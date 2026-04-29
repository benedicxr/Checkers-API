from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from ..models import Game, MoveEntry
from .ai import CheckersAIHandler
from .board import create_initial_board
from .engine import MoveContext, apply_player_move, get_pending_capture_origin
from .exceptions import GameRuleError, GameErrorCode
from .moves import get_captures_for_piece, get_valid_moves_for_piece
from .serialization import deserialize_board, serialize_board
from .types import BLACK_PLAYER, Coords, Move

_GAME_UPDATE_FIELDS = ("board", "current_turn", "status", "winner", "move_count")


@dataclass(slots=True)
class OrchestratorRuleError(Exception):
    error: GameRuleError
    game: Game | None = None

    def __str__(self) -> str:
        return str(self.error)


@transaction.atomic
def create_new_game() -> Game:
    return create_new_game_with_mode(mode=Game.Mode.VS_AI)


@transaction.atomic
def create_new_game_with_mode(*, mode: str) -> Game:
    initial_board = create_initial_board()
    return Game.objects.create(
        mode=mode,
        board=serialize_board(initial_board),
        current_turn=Game.Turn.WHITE,
        status=Game.Status.ACTIVE,
        winner=None,
        move_count=0,
    )


def get_move_history(game: Game):
    return game.moves.order_by("created_at", "id")


def get_allowed_moves(game: Game) -> list[Move]:
    if game.status != Game.Status.ACTIVE:
        return []

    board = deserialize_board(game.board)
    latest_move = _get_latest_move_context(game)
    forced_origin = get_pending_capture_origin(board, game.current_turn, latest_move)

    if forced_origin is not None:
        return get_captures_for_piece(board, game.current_turn, forced_origin)

    any_capture_available = any(
        get_captures_for_piece(board, game.current_turn, Coords(row_index, col_index))
        for row_index, row in enumerate(board)
        for col_index, board_piece in enumerate(row)
        if board_piece is not None and board_piece.color == game.current_turn
    )

    allowed_moves: list[Move] = []
    for row_index, row in enumerate(board):
        for col_index, board_piece in enumerate(row):
            if board_piece is None or board_piece.color != game.current_turn:
                continue

            origin = Coords(row_index, col_index)
            if any_capture_available:
                allowed_moves.extend(get_captures_for_piece(board, game.current_turn, origin))
            else:
                allowed_moves.extend(get_valid_moves_for_piece(board, game.current_turn, origin))

    return allowed_moves


@transaction.atomic
def process_move_request(
    game: Game,
    *,
    from_dict: dict[str, int],
    to_dict: dict[str, int],
) -> Game:
    if game.status == Game.Status.FINISHED:
        raise OrchestratorRuleError(
            GameRuleError(
                code=GameErrorCode.GAME_FINISHED,
                detail="The game is already finished.",
            )
        )

    active_player = game.current_turn
    board_before = game.board

    try:
        board = deserialize_board(game.board)
        latest_move = _get_latest_move_context(game)
        forced_origin = get_pending_capture_origin(board, active_player, latest_move)
        move_result = apply_player_move(
            board=board,
            turn=active_player,
            origin=_coords_from_payload(from_dict),
            destination=_coords_from_payload(to_dict),
            forced_origin=forced_origin,
        )
    except GameRuleError as exc:
        raise OrchestratorRuleError(exc, game=game) from exc

    MoveEntry.objects.create(
        game=game,
        player_side=active_player,
        from_pos=from_dict,
        to_pos=to_dict,
        is_jump=move_result.move.type == "capture",
        captured_pos=_coords_to_dict(move_result.move.captured),
        captured_positions=_coords_tuple_to_list(move_result.move.captured_positions),
        path=_coords_tuple_to_list(move_result.move.path or (move_result.move.from_, move_result.move.to)),
        is_promoted=move_result.is_promoted,
        board_before=board_before,
    )

    game.board = serialize_board(move_result.board)
    game.current_turn = move_result.current_turn
    game.status = move_result.status
    game.winner = move_result.winner
    game.move_count += 1
    _save_game(game, *_GAME_UPDATE_FIELDS)
    return game


@transaction.atomic
def revert_last_move(game: Game) -> Game:
    moves_to_revert = 2 if game.mode == Game.Mode.VS_AI else 1
    latest_moves = list(game.moves.order_by("-created_at", "-id")[:moves_to_revert])
    last_move = latest_moves[0] if latest_moves else None
    if last_move is None:
        raise OrchestratorRuleError(
            GameRuleError(
                code=GameErrorCode.NO_MOVES_TO_UNDO,
                detail="There are no moves to undo.",
            )
        )

    restored_move = last_move
    if (
        game.mode == Game.Mode.VS_AI
        and len(latest_moves) == 2
        and latest_moves[0].player_side == Game.Turn.BLACK
        and latest_moves[1].player_side == Game.Turn.WHITE
    ):
        restored_move = latest_moves[1]
        latest_moves[0].delete()
        latest_moves[1].delete()
        game.move_count = max(game.move_count - 2, 0)
    else:
        last_move.delete()
        game.move_count = max(game.move_count - 1, 0)

    game.board = restored_move.board_before
    game.current_turn = restored_move.player_side
    game.status = Game.Status.ACTIVE
    game.winner = None
    _save_game(game, *_GAME_UPDATE_FIELDS)
    return game


@transaction.atomic
def restart_game(game: Game) -> Game:
    initial_board = create_initial_board()

    game.board = serialize_board(initial_board)
    game.current_turn = Game.Turn.WHITE
    game.status = Game.Status.ACTIVE
    game.winner = None
    game.move_count = 0
    game.moves.all().delete()
    _save_game(game, *_GAME_UPDATE_FIELDS)
    return game


@transaction.atomic
def handle_ai_turn(game_id) -> Game:
    game = Game.objects.select_for_update().get(pk=game_id)
    if game.mode != Game.Mode.VS_AI:
        return game

    ai_handler = CheckersAIHandler()

    while game.status == Game.Status.ACTIVE and game.current_turn == BLACK_PLAYER:
        allowed_moves = get_allowed_moves(game)
        if not allowed_moves:
            break

        selected_move = ai_handler.get_best_move(game.board, allowed_moves)
        game = process_move_request(
            game,
            from_dict=_coords_to_dict(selected_move.from_),
            to_dict=_coords_to_dict(selected_move.to),
        )

    return game


def _get_latest_move_context(game: Game) -> MoveContext | None:
    latest_move = game.moves.order_by("-created_at", "-id").first()
    if latest_move is None:
        return None

    return MoveContext(
        player_side=latest_move.player_side,
        to_pos=_coords_from_payload(latest_move.to_pos),
        is_jump=latest_move.is_jump,
    )


def _coords_from_payload(payload: dict[str, int]) -> Coords:
    return Coords(r=payload["row"], c=payload["col"])


def _coords_to_dict(coords: Coords | None) -> dict[str, int] | None:
    if coords is None:
        return None
    return {"row": coords.r, "col": coords.c}


def _coords_tuple_to_list(coords_items: tuple[Coords, ...]) -> list[dict[str, int]]:
    return [_coords_to_dict(coords) for coords in coords_items]


def _save_game(game: Game, *fields: str) -> None:
    game.save(update_fields=[*fields, "updated_at"])
