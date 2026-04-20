from __future__ import annotations

from dataclasses import dataclass

from ..models import Game, MoveEntry
from .board import create_initial_board
from .engine import MoveContext, apply_player_move, get_pending_capture_origin
from .exceptions import GameRuleError, GameErrorCode
from .serialization import deserialize_board, serialize_board
from .types import Coords


@dataclass(slots=True)
class OrchestratorRuleError(Exception):
    error: GameRuleError
    game: Game | None = None

    def __str__(self) -> str:
        return str(self.error)


def create_new_game() -> Game:
    initial_board = create_initial_board()
    return Game.objects.create(
        board=serialize_board(initial_board),
        current_turn=Game.Turn.WHITE,
        status=Game.Status.ACTIVE,
        winner=None,
        move_count=0,
    )


def get_move_history(game: Game):
    return game.moves.order_by("created_at", "id")


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
    except (GameRuleError, ValueError) as exc:
        if isinstance(exc, ValueError):
            exc = GameRuleError(
                code=GameErrorCode.INVALID_BOARD_STATE,
                detail=str(exc),
            )
        raise OrchestratorRuleError(exc, game=game) from exc

    MoveEntry.objects.create(
        game=game,
        player_side=active_player,
        from_pos=from_dict,
        to_pos=to_dict,
        is_jump=move_result.move.type == "capture",
        captured_pos=_coords_to_dict(move_result.move.captured),
        is_promoted=move_result.is_promoted,
        board_before=board_before,
    )

    game.board = serialize_board(move_result.board)
    game.current_turn = move_result.current_turn
    game.status = move_result.status
    game.winner = move_result.winner
    game.move_count += 1
    _save_game(
        game,
        "board",
        "current_turn",
        "status",
        "winner",
        "move_count",
    )
    return game


def revert_last_move(game: Game) -> Game:
    last_move = game.moves.order_by("-created_at", "-id").first()
    if last_move is None:
        raise OrchestratorRuleError(
            GameRuleError(
                code=GameErrorCode.NO_MOVES_TO_UNDO,
                detail="There are no moves to undo.",
            )
        )

    game.board = last_move.board_before
    game.current_turn = last_move.player_side
    game.status = Game.Status.ACTIVE
    game.winner = None
    game.move_count = max(game.move_count - 1, 0)
    last_move.delete()
    _save_game(
        game,
        "board",
        "current_turn",
        "status",
        "winner",
        "move_count",
    )
    return game


def restart_game(game: Game) -> Game:
    initial_board = create_initial_board()

    game.board = serialize_board(initial_board)
    game.current_turn = Game.Turn.WHITE
    game.status = Game.Status.ACTIVE
    game.winner = None
    game.move_count = 0
    game.moves.all().delete()
    _save_game(
        game,
        "board",
        "current_turn",
        "status",
        "winner",
        "move_count",
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


def _save_game(game: Game, *fields: str) -> None:
    game.save(update_fields=[*fields, "updated_at"])
