from __future__ import annotations

from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from .models import Game
from .serializers import GameStateSerializer, MoveEntrySerializer, MovePayloadSerializer
from .services import orchestrator
from .services.exceptions import GameErrorCode

RULE_ERROR_STATUS_CODES = {
    GameErrorCode.GAME_FINISHED: status.HTTP_409_CONFLICT,
    GameErrorCode.NO_MOVES_TO_UNDO: status.HTTP_409_CONFLICT,
    GameErrorCode.INVALID_BOARD_STATE: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


class GameViewSet(ViewSet):
    def create(self, request: Request) -> Response:
        """POST /api/games/"""
        game = orchestrator.create_new_game()
        return _game_response(game, status_code=status.HTTP_201_CREATED)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """GET /api/games/{id}/"""
        game = self._get_game(pk)
        return _game_response(game)

    @action(detail=True, methods=["get", "post"], url_path="moves")
    def moves(self, request: Request, pk: str | None = None) -> Response:
        """GET/POST /api/games/{id}/moves/"""
        if request.method == "GET":
            game = self._get_game(pk)
            history = orchestrator.get_move_history(game)
            serializer = MoveEntrySerializer(history, many=True)
            return Response(serializer.data)

        payload = MovePayloadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        clean_data = payload.validated_data

        try:
            with transaction.atomic():
                game = self._get_game_for_update(pk)
                updated_game = orchestrator.process_move_request(
                    game,
                    from_dict=clean_data["from_pos"],
                    to_dict=clean_data["to_pos"],
                )
        except orchestrator.OrchestratorRuleError as exc:
            return _rule_error_response(exc.error, game=exc.game)

        return _game_response(updated_game)

    @action(detail=True, methods=["post"], url_path="undo")
    def undo(self, request: Request, pk: str | None = None) -> Response:
        """POST /api/games/{id}/undo/"""
        try:
            with transaction.atomic():
                game = self._get_game_for_update(pk)
                updated_game = orchestrator.revert_last_move(game)
        except orchestrator.OrchestratorRuleError as exc:
            return _rule_error_response(exc.error, game=exc.game)

        return _game_response(updated_game, status_code=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="restart")
    def restart(self, request: Request, pk: str | None = None) -> Response:
        """POST /api/games/{id}/restart/"""
        with transaction.atomic():
            game = self._get_game_for_update(pk)
            updated_game = orchestrator.restart_game(game)
        return _game_response(updated_game, status_code=status.HTTP_200_OK)

    def _get_game(self, pk: str | None) -> Game:
        return get_object_or_404(Game, pk=pk)

    def _get_game_for_update(self, pk: str | None) -> Game:
        return get_object_or_404(Game.objects.select_for_update(), pk=pk)


def _rule_error_response(exc, game=None) -> Response:
    payload: dict[str, Any] = {
        "error": {
            "code": exc.code,
            "detail": exc.detail,
        }
    }
    if game is not None:    
        payload["game"] = GameStateSerializer(game).data
    return Response(payload, status=_status_code_for_rule_error(exc.code))


def _game_response(game, *, status_code: int = status.HTTP_200_OK) -> Response:
    serializer = GameStateSerializer(game)
    return Response(serializer.data, status=status_code)


def _status_code_for_rule_error(error_code: GameErrorCode) -> int:
    return RULE_ERROR_STATUS_CODES.get(error_code, status.HTTP_400_BAD_REQUEST)
