from __future__ import annotations

from typing import Any

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from .serializers import GameStateSerializer, MoveEntrySerializer, MovePayloadSerializer
from .services import orchestrator


@api_view(["POST"])
def initialize_game(request: Request) -> Response:
    """POST /api/games/"""
    game = orchestrator.create_new_game()
    return _game_response(game, status_code=status.HTTP_201_CREATED)


@api_view(["GET"])
def fetch_game(request: Request, game_id: str) -> Response:
    """GET /api/games/{id}/"""
    game = orchestrator.get_game(game_id)
    return _game_response(game)


@api_view(["POST"])
def attempt_move(request: Request, game_id: str) -> Response:
    """POST /api/games/{id}/move/"""
    payload = MovePayloadSerializer(data=request.data)
    if not payload.is_valid():
        return _validation_error_response(payload.errors)

    clean_data = payload.validated_data
    try:
        updated_game = orchestrator.process_move_request(
            game_id,
            from_dict=clean_data["from_pos"],
            to_dict=clean_data["to_pos"],
        )
    except orchestrator.OrchestratorRuleError as exc:
        return _rule_error_response(exc.error, game=exc.game)

    return _game_response(updated_game)


@api_view(["POST"])
def undo_move(request: Request, game_id: str) -> Response:
    """POST /api/games/{id}/undo/"""
    try:
        updated_game = orchestrator.revert_last_move(game_id)
    except orchestrator.OrchestratorRuleError as exc:
        return _rule_error_response(exc.error, game=exc.game)

    return _game_response(updated_game, status_code=status.HTTP_200_OK)


@api_view(["POST"])
def restart_game(request: Request, game_id: str) -> Response:
    """POST /api/games/{id}/restart/"""
    updated_game = orchestrator.restart_game(game_id)
    return _game_response(updated_game, status_code=status.HTTP_200_OK)


@api_view(["GET"])
def fetch_moves(request: Request, game_id: str) -> Response:
    """GET /api/games/{id}/moves/"""
    history = orchestrator.get_move_history(game_id)
    serializer = MoveEntrySerializer(history, many=True)
    return Response(serializer.data)


def _validation_error_response(errors: Any) -> Response:
    return Response(
        {
            "error": {
                "code": "validation_error",
                "detail": "The request payload is invalid.",
                "fields": errors,
            }
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def _rule_error_response(exc, game=None) -> Response:
    payload: dict[str, Any] = {
        "error": {
            "code": exc.code,
            "detail": exc.detail,
        }
    }
    if exc.extra:
        payload["error"].update(exc.extra)
    if game is not None:
        payload["game"] = GameStateSerializer(game).data
    return Response(payload, status=exc.status_code)


def _game_response(game, *, status_code: int = status.HTTP_200_OK) -> Response:
    serializer = GameStateSerializer(game)
    return Response(serializer.data, status=status_code)
