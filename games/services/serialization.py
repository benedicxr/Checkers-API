from __future__ import annotations

from typing import Any

from .types import BLACK_PLAYER, Board, COLS, Piece, ROWS, WHITE_PLAYER


def serialize_piece(piece: Piece | None) -> dict[str, Any] | None:
    if piece is None:
        return None

    return {
        "id": piece.id,
        "color": piece.color,
        "is_king": piece.is_king,
    }


def deserialize_piece(piece_data: dict[str, Any] | None) -> Piece | None:
    if piece_data is None:
        return None

    color = piece_data["color"]
    if color not in {WHITE_PLAYER, BLACK_PLAYER}:
        raise ValueError(f"Unsupported piece color: {color}")

    return Piece(
        id=int(piece_data["id"]),
        color=color,
        is_king=bool(piece_data.get("is_king", False)),
    )


def serialize_board(board: Board) -> list[list[dict[str, Any] | None]]:
    if len(board) != ROWS or any(len(row) != COLS for row in board):
        raise ValueError("Board must be an 8x8 matrix.")

    return [
        [serialize_piece(piece) for piece in row]
        for row in board
    ]


def deserialize_board(board_data: list[list[dict[str, Any] | None]]) -> Board:
    if len(board_data) != ROWS or any(len(row) != COLS for row in board_data):
        raise ValueError("Board JSON must be an 8x8 matrix.")

    return [
        [deserialize_piece(piece_data) for piece_data in row]
        for row in board_data
    ]
