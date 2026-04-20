from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .board import get_piece
from .exceptions import GameErrorCode, GameRuleError
from .game import count_pieces, get_winner_by_board
from .moves import apply_move, get_captures_for_piece, get_valid_moves_for_piece
from .types import BLACK_PLAYER, Board, Coords, Move, Player, WHITE_PLAYER

ACTIVE_STATUS = "active"
FINISHED_STATUS = "finished"


@dataclass(frozen=True, slots=True)
class MoveContext:
    player_side: Player
    to_pos: Coords
    is_jump: bool


@dataclass(frozen=True, slots=True)
class MoveResolution:
    board: Board
    move: Move
    current_turn: Player
    status: str
    winner: Optional[Player]
    is_promoted: bool


def other_player(player: Player) -> Player:
    return BLACK_PLAYER if player == WHITE_PLAYER else WHITE_PLAYER


def get_pending_capture_origin(
    board: Board,
    current_turn: Player,
    latest_move: MoveContext | None,
) -> Coords | None:
    if latest_move is None:
        return None
    if latest_move.player_side != current_turn or not latest_move.is_jump:
        return None
    if get_piece(board, latest_move.to_pos.r, latest_move.to_pos.c) is None:
        return None

    follow_up_captures = get_captures_for_piece(board, current_turn, latest_move.to_pos)
    if not follow_up_captures:
        return None

    return latest_move.to_pos


def apply_player_move(
    *,
    board: Board,
    turn: Player,
    origin: Coords,
    destination: Coords,
    forced_origin: Coords | None = None,
) -> MoveResolution:
    piece = get_piece(board, origin.r, origin.c)
    if piece is None:
        raise GameRuleError(
            code=GameErrorCode.PIECE_NOT_FOUND,
            detail="No piece was found at the selected origin square.",
        )
    if piece.color != turn:
        raise GameRuleError(
            code=GameErrorCode.WRONG_TURN,
            detail="The selected piece does not belong to the active player.",
        )

    if forced_origin is not None and origin != forced_origin:
        raise GameRuleError(
            code=GameErrorCode.CAPTURE_CONTINUATION_REQUIRED,
            detail="The current capture chain must continue with the same piece.",
        )

    captures_for_origin = get_captures_for_piece(board, turn, origin)
    any_capture_available = any(
        get_captures_for_piece(board, turn, Coords(row_index, col_index))
        for row_index, row in enumerate(board)
        for col_index, board_piece in enumerate(row)
        if board_piece is not None and board_piece.color == turn
    )

    legal_moves = captures_for_origin if any_capture_available else get_valid_moves_for_piece(board, turn, origin)

    if any_capture_available and not captures_for_origin:
        raise GameRuleError(
            code=GameErrorCode.MANDATORY_CAPTURE,
            detail="A capture is available and must be played.",
        )

    selected_move: Move | None = None
    for legal_move in legal_moves:
        if legal_move.to == destination:
            selected_move = legal_move
            break

    if selected_move is None:
        raise GameRuleError(
            code=GameErrorCode.ILLEGAL_MOVE,
            detail="The requested move is not legal in the current position.",
        )

    next_board = apply_move(board, selected_move)
    moved_piece = get_piece(next_board, selected_move.to.r, selected_move.to.c)
    is_promoted = bool(piece is not None and moved_piece is not None and not piece.is_king and moved_piece.is_king)

    opponent = other_player(turn)
    if count_pieces(next_board, opponent) == 0:
        return MoveResolution(
            board=next_board,
            move=selected_move,
            current_turn=turn,
            status=FINISHED_STATUS,
            winner=turn,
            is_promoted=is_promoted,
        )

    must_continue = selected_move.type == "capture" and bool(get_captures_for_piece(next_board, turn, selected_move.to))
    if must_continue:
        return MoveResolution(
            board=next_board,
            move=selected_move,
            current_turn=turn,
            status=ACTIVE_STATUS,
            winner=None,
            is_promoted=is_promoted,
        )

    next_turn = other_player(turn)
    winner = get_winner_by_board(next_board, next_turn)

    if winner is not None:
        return MoveResolution(
            board=next_board,
            move=selected_move,
            current_turn=turn,
            status=FINISHED_STATUS,
            winner=winner,
            is_promoted=is_promoted,
        )

    return MoveResolution(
        board=next_board,
        move=selected_move,
        current_turn=next_turn,
        status=ACTIVE_STATUS,
        winner=None,
        is_promoted=is_promoted,
    )
