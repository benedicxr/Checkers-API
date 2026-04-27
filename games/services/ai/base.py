from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from ..types import Move


class BaseMoveSelector(ABC):
    provider_name = "base"

    def __init__(self, *, model: str):
        self.model = model

    def get_best_move(
        self,
        board_state: list[list[dict[str, Any] | None]],
        allowed_moves: list[Move],
    ) -> Move:
        if not allowed_moves:
            raise ValueError("allowed_moves must contain at least one move.")

        if not self.is_available():
            return allowed_moves[0]

        indexed_moves = self._index_moves(allowed_moves)

        try:
            raw_content = self.request_move_index(
                board_state=board_state,
                indexed_moves=indexed_moves,
            )
        except Exception as exc:
            return allowed_moves[0]

        move_index = self.extract_index(raw_content, len(allowed_moves))
        return allowed_moves[move_index] if move_index is not None else allowed_moves[0]

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def request_move_index(
        self,
        *,
        board_state: list[list[dict[str, Any] | None]],
        indexed_moves: list[dict[str, Any]],
    ) -> Any:
        raise NotImplementedError

    def build_prompt(
        self,
        *,
        board_state: list[list[dict[str, Any] | None]],
        indexed_moves: list[dict[str, Any]],
    ) -> str:
        return (
            "You are a professional checkers player.\n"
            "Choose the strongest move from the provided legal moves.\n"
            "Return only the numeric index of the chosen move.\n\n"
            "Current board state JSON:\n"
            f"{json.dumps(board_state, ensure_ascii=True)}\n\n"
            "Legal moves JSON:\n"
            f"{json.dumps(indexed_moves, ensure_ascii=True)}\n\n"
            "Return only the index."
        )

    @staticmethod
    def extract_index(raw_content: Any, total_moves: int) -> int | None:
        if not isinstance(raw_content, str):
            return None

        candidate = raw_content.strip()
        if not candidate:
            return None

        try:
            index = int(candidate)
        except ValueError:
            digits = "".join(ch for ch in candidate if ch.isdigit())
            if not digits:
                return None
            index = int(digits)

        if 0 <= index < total_moves:
            return index
        return None

    @staticmethod
    def _index_moves(allowed_moves: list[Move]) -> list[dict[str, Any]]:
        return [
            {
                "index": index,
                "from": {"row": move.from_.r, "col": move.from_.c},
                "to": {"row": move.to.r, "col": move.to.c},
                "type": move.type,
                "captured": None if move.captured is None else {"row": move.captured.r, "col": move.captured.c},
            }
            for index, move in enumerate(allowed_moves)
        ]
