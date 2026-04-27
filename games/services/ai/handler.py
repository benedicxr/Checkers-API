from __future__ import annotations

import os

from .base import BaseMoveSelector
from .providers import GeminiMoveSelector

DEFAULT_AI_BACKEND = (os.environ.get("CHECKERS_AI_BACKEND") or "gemini").strip()
DEFAULT_AI_MODEL = (os.environ.get("CHECKERS_AI_MODEL") or "gemini-2.5-flash").strip()


class CheckersAIHandler(BaseMoveSelector):
    def __init__(
        self,
        *,
        backend: str = DEFAULT_AI_BACKEND,
        model: str = DEFAULT_AI_MODEL,
    ):
        super().__init__(model=model)
        self.backend = (backend or "gemini").strip().lower()
        self._selector = build_move_selector(backend=self.backend, model=model)

    def is_available(self) -> bool:
        return self._selector.is_available()

    def request_move_index(self, **kwargs):
        return self._selector.request_move_index(**kwargs)

    def get_best_move(self, board_state, allowed_moves):
        return self._selector.get_best_move(board_state, allowed_moves)


def build_move_selector(*, backend: str, model: str) -> BaseMoveSelector:
    registry: dict[str, type[BaseMoveSelector]] = {
        "gemini": GeminiMoveSelector,
    }
    selector_cls = registry.get((backend or "gemini").strip().lower())
    if selector_cls is None:
        raise ValueError(f"Unsupported AI backend: {backend}")
    return selector_cls(model=model)
