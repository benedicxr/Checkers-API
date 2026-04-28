from __future__ import annotations

import os

from ..types import Move
from .base import BaseProvider, BoardState, IndexedMoves
from .providers import GeminiProvider, GroqProvider, OpenRouterProvider

DEFAULT_AI_BACKEND = (os.environ.get("CHECKERS_AI_BACKEND") or "gemini").strip()
DEFAULT_AI_MODEL = (os.environ.get("CHECKERS_AI_MODEL") or "gemini-2.5-flash").strip()


class CheckersAIHandler(BaseProvider):
    def __init__(
        self,
        *,
        backend: str = DEFAULT_AI_BACKEND,
        model: str = DEFAULT_AI_MODEL,
    ):
        super().__init__(model=model)
        self.backend = (backend or "gemini").strip().lower()
        self._provider = build_provider(backend=self.backend, model=model)

    def is_available(self) -> bool:
        return self._provider.is_available()

    def request_move_index(
        self,
        *,
        board_state: BoardState,
        indexed_moves: IndexedMoves,
    ) -> str | None:
        return self._provider.request_move_index(
            board_state=board_state,
            indexed_moves=indexed_moves,
        )

    def get_best_move(self, board_state: BoardState, allowed_moves: list[Move]) -> Move:
        return self._provider.get_best_move(board_state, allowed_moves)


def build_provider(*, backend: str, model: str) -> BaseProvider:
    registry: dict[str, type[BaseProvider]] = {
        "gemini": GeminiProvider,
        "openrouter": OpenRouterProvider,
        "groq": GroqProvider,
    }
    provider_cls = registry.get((backend or "gemini").strip().lower())
    if provider_cls is None:
        raise ValueError(f"Unsupported AI backend: {backend}")
    return provider_cls(model=model)
