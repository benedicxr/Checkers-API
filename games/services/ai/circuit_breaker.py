from __future__ import annotations

import json
from dataclasses import dataclass
from time import time
from typing import Callable, Protocol

import django_rq


STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerConfig:
    enabled: bool = True
    failure_threshold: int = 2
    recovery_timeout: int = 120


@dataclass(frozen=True)
class CircuitBreakerState:
    status: str = STATE_CLOSED
    failure_count: int = 0
    opened_at: float | None = None


@dataclass(frozen=True)
class CircuitBreakerDecision:
    allowed: bool
    state: str
    transition: str | None = None


class CircuitBreakerStore(Protocol):
    def load(self, key: str) -> CircuitBreakerState:
        raise NotImplementedError

    def save(self, key: str, state: CircuitBreakerState) -> None:
        raise NotImplementedError


class RedisCircuitBreakerStore:
    def __init__(self, *, key_prefix: str = "ai_circuit_breaker", queue_name: str = "default"):
        self.key_prefix = key_prefix
        self.queue_name = queue_name
        self._fallback_store = InMemoryCircuitBreakerStore()

    def load(self, key: str) -> CircuitBreakerState:
        try:
            payload = self._connection().get(self._redis_key(key))
        except Exception:
            return self._fallback_store.load(key)

        if payload is None:
            return CircuitBreakerState()

        try:
            decoded_payload = json.loads(payload)
        except (TypeError, ValueError):
            return CircuitBreakerState()

        if not isinstance(decoded_payload, dict):
            return CircuitBreakerState()

        status = decoded_payload.get("status")
        failure_count = decoded_payload.get("failure_count")
        opened_at = decoded_payload.get("opened_at")
        if status not in {STATE_CLOSED, STATE_OPEN, STATE_HALF_OPEN}:
            return CircuitBreakerState()
        if not isinstance(failure_count, int):
            return CircuitBreakerState()
        if opened_at is not None and not isinstance(opened_at, (int, float)):
            return CircuitBreakerState()

        return CircuitBreakerState(
            status=status,
            failure_count=failure_count,
            opened_at=None if opened_at is None else float(opened_at),
        )

    def save(self, key: str, state: CircuitBreakerState) -> None:
        try:
            self._connection().set(
                self._redis_key(key),
                json.dumps(
                    {
                        "status": state.status,
                        "failure_count": state.failure_count,
                        "opened_at": state.opened_at,
                    }
                ),
            )
        except Exception:
            self._fallback_store.save(key, state)

    def _redis_key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def _connection(self):
        return django_rq.get_connection(self.queue_name)


class InMemoryCircuitBreakerStore:
    def __init__(self):
        self._state_by_key: dict[str, CircuitBreakerState] = {}

    def load(self, key: str) -> CircuitBreakerState:
        return self._state_by_key.get(key, CircuitBreakerState())

    def save(self, key: str, state: CircuitBreakerState) -> None:
        self._state_by_key[key] = state


class CircuitBreaker:
    def __init__(
        self,
        *,
        store: CircuitBreakerStore | None = None,
        config: CircuitBreakerConfig | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._store = store or RedisCircuitBreakerStore()
        self.config = config or CircuitBreakerConfig()
        self._clock = clock or time

    def allow_request(self, provider_name: str, model: str) -> CircuitBreakerDecision:
        if not self.config.enabled:
            return CircuitBreakerDecision(allowed=True, state=STATE_CLOSED)

        key = self._state_key(provider_name, model)
        state = self._store.load(key)

        if state.status == STATE_CLOSED:
            return CircuitBreakerDecision(allowed=True, state=STATE_CLOSED)

        if state.status == STATE_HALF_OPEN:
            return CircuitBreakerDecision(allowed=False, state=STATE_HALF_OPEN)

        if state.opened_at is None:
            return CircuitBreakerDecision(allowed=False, state=STATE_OPEN)

        if (self._clock() - state.opened_at) < self.config.recovery_timeout:
            return CircuitBreakerDecision(allowed=False, state=STATE_OPEN)

        half_open_state = CircuitBreakerState(
            status=STATE_HALF_OPEN,
            failure_count=state.failure_count,
            opened_at=state.opened_at,
        )
        self._store.save(key, half_open_state)
        return CircuitBreakerDecision(
            allowed=True,
            state=STATE_HALF_OPEN,
            transition=STATE_HALF_OPEN,
        )

    def record_success(self, provider_name: str, model: str) -> str | None:
        if not self.config.enabled:
            return None

        key = self._state_key(provider_name, model)
        previous_state = self._store.load(key)
        self._store.save(key, CircuitBreakerState())

        if previous_state.status != STATE_CLOSED or previous_state.failure_count:
            return STATE_CLOSED
        return None

    def record_failure(self, provider_name: str, model: str) -> str | None:
        if not self.config.enabled:
            return None

        key = self._state_key(provider_name, model)
        previous_state = self._store.load(key)

        if previous_state.status == STATE_HALF_OPEN:
            self._store.save(
                key,
                CircuitBreakerState(
                    status=STATE_OPEN,
                    failure_count=max(self.config.failure_threshold, previous_state.failure_count),
                    opened_at=self._clock(),
                ),
            )
            return STATE_OPEN

        next_failure_count = previous_state.failure_count + 1
        if next_failure_count >= self.config.failure_threshold:
            self._store.save(
                key,
                CircuitBreakerState(
                    status=STATE_OPEN,
                    failure_count=next_failure_count,
                    opened_at=self._clock(),
                ),
            )
            return STATE_OPEN

        self._store.save(
            key,
            CircuitBreakerState(
                status=STATE_CLOSED,
                failure_count=next_failure_count,
                opened_at=None,
            ),
        )
        return None

    @staticmethod
    def _state_key(provider_name: str, model: str) -> str:
        return f"{provider_name}:{model}"
