from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Player = Literal["white", "black"]
Color = Player

ROWS: int = 8
COLS: int = 8
WHITE_PLAYER: Player = "white"
BLACK_PLAYER: Player = "black"

INITIAL_PIECE_ROWS: int = 3
MOVE_STEP: int = 1
JUMP_STEP: int = 2

WHITE_DIRECTION: int = -1
BLACK_DIRECTION: int = 1
SIDES: tuple[int, int] = (-1, 1)

MEN_CAN_CAPTURE_BACKWARDS: bool = True
FLYING_KINGS: bool = True


@dataclass(frozen=True, slots=True)
class Coords:
    r: int
    c: int


@dataclass(frozen=True, slots=True)
class Piece:
    id: int
    color: Color
    is_king: bool = False


@dataclass(frozen=True, slots=True)
class Move:
    type: Literal["simple", "capture"]
    from_: Coords
    to: Coords
    captured: Optional[Coords] = None


Board = list[list[Optional[Piece]]]
