from __future__ import annotations

from typing import Optional

from .board import get_piece, is_inside
from .types import (
    BLACK_DIRECTION,
    BLACK_PLAYER,
    Coords,
    FLYING_KINGS,
    JUMP_STEP,
    MEN_CAN_CAPTURE_BACKWARDS,
    MOVE_STEP,
    Piece,
    Player,
    ROWS,
    SIDES,
    WHITE_DIRECTION,
    WHITE_PLAYER,
    Board,
    Move,
)


def get_quiet_moves_for_piece(board: Board, turn: Player, origin: Coords) -> list[Move]:
    piece = get_piece(board, origin.r, origin.c)
    if piece is None or piece.color != turn:
        return []

    moves: list[Move] = []

    if piece.is_king and FLYING_KINGS:
        diagonals = ((-1, -1), (-1, 1), (1, -1), (1, 1))
        for dr, dc in diagonals:
            r = origin.r + dr
            c = origin.c + dc
            while is_inside(r, c) and get_piece(board, r, c) is None:
                moves.append(Move(type="simple", from_=origin, to=Coords(r, c)))
                r += dr
                c += dc
        return moves

    if piece.is_king:
        directions = (WHITE_DIRECTION, BLACK_DIRECTION)
    else:
        directions = (WHITE_DIRECTION,) if piece.color == WHITE_PLAYER else (BLACK_DIRECTION,)

    for dir_ in directions:
        for side in SIDES:
            to = Coords(origin.r + dir_ * MOVE_STEP, origin.c + side)
            if is_inside(to.r, to.c) and get_piece(board, to.r, to.c) is None:
                moves.append(Move(type="simple", from_=origin, to=to))

    return moves


def get_captures_for_piece(board: Board, turn: Player, origin: Coords) -> list[Move]:
    piece = get_piece(board, origin.r, origin.c)
    if piece is None or piece.color != turn:
        return []

    captures: list[Move] = []

    if piece.is_king and FLYING_KINGS:
        diagonals = ((-1, -1), (-1, 1), (1, -1), (1, 1))

        for dr, dc in diagonals:
            r = origin.r + dr
            c = origin.c + dc

            while is_inside(r, c) and get_piece(board, r, c) is None:
                r += dr
                c += dc

            if not is_inside(r, c):
                continue

            target = get_piece(board, r, c)
            if target is None or target.color == piece.color:
                continue

            land_r = r + dr
            land_c = c + dc
            while is_inside(land_r, land_c) and get_piece(board, land_r, land_c) is None:
                captures.append(
                    Move(
                        type="capture",
                        from_=origin,
                        to=Coords(land_r, land_c),
                        captured=Coords(r, c),
                    )
                )
                land_r += dr
                land_c += dc

        return captures

    if piece.is_king:
        directions = (WHITE_DIRECTION, BLACK_DIRECTION)
    elif MEN_CAN_CAPTURE_BACKWARDS:
        directions = (WHITE_DIRECTION, BLACK_DIRECTION)
    else:
        directions = (WHITE_DIRECTION,) if piece.color == WHITE_PLAYER else (BLACK_DIRECTION,)

    for dir_ in directions:
        for side in SIDES:
            mid = Coords(origin.r + dir_ * MOVE_STEP, origin.c + side)
            to = Coords(origin.r + dir_ * JUMP_STEP, origin.c + side * JUMP_STEP)

            if not is_inside(to.r, to.c):
                continue
            if get_piece(board, to.r, to.c) is not None:
                continue

            middle_piece = get_piece(board, mid.r, mid.c)
            if middle_piece is not None and middle_piece.color != piece.color:
                captures.append(Move(type="capture", from_=origin, to=to, captured=mid))

    return captures


def get_valid_moves_for_piece(board: Board, turn: Player, origin: Coords, *, captures_only: bool = False) -> list[Move]:
    piece = get_piece(board, origin.r, origin.c)
    if piece is None or piece.color != turn:
        return []

    captures = get_captures_for_piece(board, turn, origin)
    if captures_only:
        return captures

    quiet = get_quiet_moves_for_piece(board, turn, origin)
    return [*captures, *quiet]


def apply_move(board: Board, move: Move) -> Board:
    next_b = [row[:] for row in board]

    piece = get_piece(next_b, move.from_.r, move.from_.c)
    if piece is None:
        return next_b

    next_b[move.from_.r][move.from_.c] = None
    next_b[move.to.r][move.to.c] = piece

    if move.type == "capture" and move.captured is not None:
        next_b[move.captured.r][move.captured.c] = None

    placed = next_b[move.to.r][move.to.c]
    if placed is not None and not placed.is_king:
        if placed.color == WHITE_PLAYER and move.to.r == 0:
            next_b[move.to.r][move.to.c] = Piece(id=placed.id, color=placed.color, is_king=True)
        elif placed.color == BLACK_PLAYER and move.to.r == ROWS - 1:
            next_b[move.to.r][move.to.c] = Piece(id=placed.id, color=placed.color, is_king=True)

    return next_b
