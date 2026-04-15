from __future__ import annotations

from typing import Optional

from .types import (
    BLACK_PLAYER,
    Board,
    COLS,
    INITIAL_PIECE_ROWS,
    Piece,
    ROWS,
    WHITE_PLAYER,
)


def is_inside(r: int, c: int) -> bool:
    return 0 <= r < ROWS and 0 <= c < COLS


def get_piece(board: Board, r: int, c: int) -> Optional[Piece]:
    if not is_inside(r, c):
        return None
    return board[r][c]


def create_initial_board() -> Board:
    board: Board = [[None for _ in range(COLS)] for _ in range(ROWS)]
    next_id = 1

    for r in range(ROWS):
        for c in range(COLS):
            if (r + c) % 2 != 1:
                continue

            if r < INITIAL_PIECE_ROWS:
                board[r][c] = Piece(id=next_id, color=BLACK_PLAYER, is_king=False)
                next_id += 1
            elif r >= ROWS - INITIAL_PIECE_ROWS:
                board[r][c] = Piece(id=next_id, color=WHITE_PLAYER, is_king=False)
                next_id += 1

    return board
