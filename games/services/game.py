from __future__ import annotations

from typing import Optional

from .moves import get_captures_for_piece, get_quiet_moves_for_piece
from .types import BLACK_PLAYER, Board, Coords, Player, ROWS, WHITE_PLAYER


def get_winner_by_board(board: Board, turn: Player) -> Optional[Player]:
    white_count = 0
    black_count = 0

    for r in range(ROWS):
        for c in range(len(board[r])):
            p = board[r][c]
            if p is None:
                continue
            if p.color == WHITE_PLAYER:
                white_count += 1
            else:
                black_count += 1

    if white_count == 0 and black_count == 0:
        return None
    if white_count == 0:
        return BLACK_PLAYER
    if black_count == 0:
        return WHITE_PLAYER

    for r in range(ROWS):
        for c in range(len(board[r])):
            p = board[r][c]
            if p is None or p.color != turn:
                continue
            if get_captures_for_piece(board, turn, Coords(r, c)) or get_quiet_moves_for_piece(board, turn, Coords(r, c)):
                return None

    return BLACK_PLAYER if turn == WHITE_PLAYER else WHITE_PLAYER
