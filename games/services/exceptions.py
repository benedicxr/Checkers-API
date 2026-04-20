from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GameErrorCode(StrEnum):
    GAME_FINISHED = "game_finished"
    NO_MOVES_TO_UNDO = "no_moves_to_undo"
    INVALID_BOARD_STATE = "invalid_board_state"
    PIECE_NOT_FOUND = "piece_not_found"
    WRONG_TURN = "wrong_turn"
    CAPTURE_CONTINUATION_REQUIRED = "capture_continuation_required"
    MANDATORY_CAPTURE = "mandatory_capture"
    ILLEGAL_MOVE = "illegal_move"


@dataclass(slots=True)
class GameRuleError(Exception):
    code: GameErrorCode
    detail: str

    def __str__(self) -> str:
        return self.detail
