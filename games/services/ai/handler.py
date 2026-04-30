from __future__ import annotations

import logging
import os
from collections import Counter

from ..types import Move
from .base import (
    BaseProvider,
    BoardState,
    IndexedMoves,
    ProviderError,
    ProviderInvalidResponse,
    ProviderRequestFailed,
)
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .providers import (
    FirstLegalMoveProvider,
    GeminiProvider,
    GroqProvider,
    OpenRouterProvider,
)

logger = logging.getLogger(__name__)

DEFAULT_AI_BACKEND = (os.environ.get("CHECKERS_AI_BACKEND") or "gemini").strip()
DEFAULT_AI_MODEL = (os.environ.get("CHECKERS_AI_MODEL") or "gemini-2.5-flash").strip()
DEFAULT_CB_ENABLED = (os.environ.get("CHECKERS_AI_CB_ENABLED") or "true").strip().lower() not in {"0", "false", "no"}
DEFAULT_CB_FAILURE_THRESHOLD = int(os.environ.get("CHECKERS_AI_CB_FAILURE_THRESHOLD", "2"))
DEFAULT_CB_RECOVERY_TIMEOUT = int(os.environ.get("CHECKERS_AI_CB_RECOVERY_TIMEOUT", "120"))

_AI_PROVIDER_METRICS: Counter[str] = Counter()

_PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
    "groq": GroqProvider,
}


class CheckersAIHandler:
    def __init__(
        self,
        *,
        backend: str = DEFAULT_AI_BACKEND,
        model: str = DEFAULT_AI_MODEL,
        providers: list[BaseProvider] | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        self.backend = (backend or "gemini").strip().lower()
        self.model = model
        self._providers = providers or build_provider_chain(backend=self.backend, model=model)
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            config=CircuitBreakerConfig(
                enabled=DEFAULT_CB_ENABLED,
                failure_threshold=max(1, DEFAULT_CB_FAILURE_THRESHOLD),
                recovery_timeout=max(1, DEFAULT_CB_RECOVERY_TIMEOUT),
            ),
        )

    def is_available(self) -> bool:
        return any(provider.is_available() for provider in self._providers)

    def request_move_index(
        self,
        *,
        board_state: BoardState,
        indexed_moves: IndexedMoves,
    ) -> str | None:
        for provider in self._providers:
            if not provider.is_available():
                continue
            return provider.request_move_index(
                board_state=board_state,
                indexed_moves=indexed_moves,
            )
        return None

    def get_best_move(self, board_state: BoardState, allowed_moves: list[Move]) -> Move:
        if not allowed_moves:
            raise ValueError("allowed_moves must contain at least one move.")

        for provider in self._providers:
            if self._should_skip_provider(provider):
                continue

            try:
                selected_move = provider.get_best_move(board_state, allowed_moves)
            except ProviderError as exc:
                self._record_provider_failure(provider, exc)
                if self._is_circuit_breaker_eligible(provider) and _is_breaker_worthy(exc):
                    transition = self._circuit_breaker.record_failure(provider.provider_name, provider.model)
                    self._log_circuit_breaker_transition(provider, transition)
                continue

            self._record_provider_success(provider)
            if self._is_circuit_breaker_eligible(provider):
                transition = self._circuit_breaker.record_success(provider.provider_name, provider.model)
                self._log_circuit_breaker_transition(provider, transition)
            return selected_move

        raise RuntimeError("No AI provider was able to select a move.")

    def _should_skip_provider(self, provider: BaseProvider) -> bool:
        if not self._is_circuit_breaker_eligible(provider):
            return False

        decision = self._circuit_breaker.allow_request(provider.provider_name, provider.model)
        self._log_circuit_breaker_transition(provider, decision.transition)
        if decision.allowed:
            return False

        _increment_metric(provider.provider_name, "circuit_open")
        logger.warning(
            "AI provider circuit breaker blocked request.",
            extra={
                "provider": provider.provider_name,
                "backend": self.backend,
                "model": provider.model,
                "breaker_state": decision.state,
            },
        )
        return True

    def _record_provider_failure(self, provider: BaseProvider, exc: ProviderError) -> None:
        _increment_metric(provider.provider_name, "failure")
        logger.warning(
            "AI provider failed; falling through to next provider.",
            extra={
                "provider": provider.provider_name,
                "backend": self.backend,
                "model": provider.model,
                "error_type": type(exc).__name__,
            },
            exc_info=exc,
        )

    def _record_provider_success(self, provider: BaseProvider) -> None:
        _increment_metric(provider.provider_name, "success")
        logger.warning(
            "AI provider selected move: %s (%s)", provider.provider_name, provider.model,
            extra={
                "provider": provider.provider_name,
                "backend": self.backend,
                "model": provider.model,
            },
        )
        if isinstance(provider, FirstLegalMoveProvider):
            logger.warning(
                "AI provider chain exhausted; using terminal fallback provider.",
                extra={
                    "provider": provider.provider_name,
                    "backend": self.backend,
                    "model": provider.model,
                },
            )

    @staticmethod
    def _is_circuit_breaker_eligible(provider: BaseProvider) -> bool:
        return not isinstance(provider, FirstLegalMoveProvider)

    def _log_circuit_breaker_transition(self, provider: BaseProvider, transition: str | None) -> None:
        if transition is None:
            return

        logger.warning(
            "AI provider circuit breaker transitioned state.",
            extra={
                "provider": provider.provider_name,
                "backend": self.backend,
                "model": provider.model,
                "breaker_state": transition,
            },
        )


def build_provider(*, backend: str, model: str) -> BaseProvider:
    provider_cls = _PROVIDER_REGISTRY.get((backend or "gemini").strip().lower())
    if provider_cls is None:
        raise ValueError(f"Unsupported AI backend: {backend}")
    return provider_cls(model=model)


def build_provider_chain(*, backend: str, model: str) -> list[BaseProvider]:
    provider_names = _ordered_provider_names(backend)
    providers = [
        build_provider(
            backend=provider_name,
            model=_resolve_provider_model(provider_name, default_model=model),
        )
        for provider_name in provider_names
    ]
    providers.append(FirstLegalMoveProvider())
    return providers


def get_primary_provider(*, backend: str, model: str) -> BaseProvider:
    primary_provider_name = _ordered_provider_names(backend)[0]
    return build_provider(
        backend=primary_provider_name,
        model=_resolve_provider_model(primary_provider_name, default_model=model),
    )


def _ordered_provider_names(backend: str) -> list[str]:
    raw_names = [(name or "").strip().lower() for name in backend.split(",")]
    configured_names = [name for name in raw_names if name]
    if not configured_names:
        configured_names = ["gemini"]

    ordered_names: list[str] = []
    for provider_name in configured_names:
        if provider_name in ordered_names:
            continue
        if provider_name not in _PROVIDER_REGISTRY:
            raise ValueError(f"Unsupported AI backend: {provider_name}")
        ordered_names.append(provider_name)

    return ordered_names


def _increment_metric(provider_name: str, outcome: str) -> None:
    _AI_PROVIDER_METRICS[f"{provider_name}.{outcome}"] += 1


def _resolve_provider_model(provider_name: str, *, default_model: str) -> str:
    env_var_name = f"CHECKERS_AI_MODEL_{provider_name.upper()}"
    provider_model = (os.environ.get(env_var_name) or "").strip()
    if provider_model:
        return provider_model
    return default_model


def _is_breaker_worthy(exc: ProviderError) -> bool:
    return isinstance(exc, (ProviderRequestFailed, ProviderInvalidResponse))
