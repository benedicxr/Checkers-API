from __future__ import annotations

from typing import Optional

from .types import (
    BLACK_PLAYER,
    Board,
    COLS,
    Coords,
    INITIAL_PIECE_ROWS,
    InitialState,
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


def create_initial_board() -> InitialState:
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

    return InitialState(board=board, next_id=next_id)


def format_board(board: Board) -> str:
    header = "   " + " ".join(chr(ord("a") + c) for c in range(COLS))
    lines = [header]

    for r in range(ROWS):
        symbols: list[str] = []
        for c in range(COLS):
            piece = board[r][c]
            if piece is None:
                symbols.append(".")
                continue

            symbol = "w" if piece.color == WHITE_PLAYER else "b"
            if piece.is_king:
                symbol = symbol.upper()
            symbols.append(symbol)

        lines.append(f"{r + 1:>2}  " + " ".join(symbols))

    return "\n".join(lines)


def print_board(board: Board) -> None:
    print(format_board(board))
