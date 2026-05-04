from __future__ import annotations

import django_rq
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.http import Http404
from rq.job import Job
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from .models import Game
from .serializers import GameCreateSerializer, GameStateSerializer, MoveEntrySerializer, MovePayloadSerializer
from .services import orchestrator
from .tasks import process_ai_turn_task


class GameViewSet(ViewSet):
    def create(self, request: Request) -> Response:
        """POST /api/games/"""
        payload = GameCreateSerializer(data=request.data or {})
        payload.is_valid(raise_exception=True)
        game = orchestrator.create_new_game_with_mode(mode=payload.validated_data["mode"])
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

        game = self._get_game_for_update(pk)
        updated_game = orchestrator.process_move_request(
            game,
            from_dict=clean_data["from_pos"],
            to_dict=clean_data["to_pos"],
        )
        ai_response = _maybe_process_ai_turn(updated_game)
        if ai_response is not None:
            return ai_response

        return _game_response(updated_game)

    @action(detail=True, methods=["post"], url_path="undo")
    def undo(self, request: Request, pk: str | None = None) -> Response:
        """POST /api/games/{id}/undo/"""
        game = self._get_game_for_update(pk)
        updated_game = orchestrator.revert_last_move(game)
        return _game_response(updated_game, status_code=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="restart")
    def restart(self, request: Request, pk: str | None = None) -> Response:
        """POST /api/games/{id}/restart/"""
        game = self._get_game_for_update(pk)
        updated_game = orchestrator.restart_game(game)
        return _game_response(updated_game, status_code=status.HTTP_200_OK)

    def _get_game(self, pk: str | None) -> Game:
        try:
            return get_object_or_404(Game, pk=pk)
        except (ValueError, ValidationError):
            raise Http404

    def _get_game_for_update(self, pk: str | None) -> Game:
        try:
            return get_object_or_404(Game.objects.select_for_update(), pk=pk)
        except (ValueError, ValidationError):
            raise Http404


def _game_response(game, *, status_code: int = status.HTTP_200_OK) -> Response:
    serializer = GameStateSerializer(game)
    return Response(serializer.data, status=status_code)


def _maybe_process_ai_turn(game: Game) -> Response | None:
    if (
        game.mode != Game.Mode.VS_AI
        or game.status != Game.Status.ACTIVE
        or game.current_turn != Game.Turn.BLACK
    ):
        return None

    allowed_moves = orchestrator.get_allowed_moves(game)
    if len(allowed_moves) <= 1:
        updated_game = orchestrator.handle_ai_turn(game.pk)
        return _game_response(updated_game)

    job = process_ai_turn_task.delay(str(game.pk))
    serializer = GameStateSerializer(game)
    return Response(
        {
            "taskId": job.id,
            "status": "queued",
            "game": serializer.data,
        },
        status=status.HTTP_202_ACCEPTED,
    )


class TaskStatusView(APIView):
    def get(self, request: Request, task_id: str) -> Response:
        try:
            job = Job.fetch(task_id, connection=django_rq.get_connection("default"))
        except Exception as exc:
            raise NotFound(detail="Task not found.") from exc

        job_status = job.get_status(refresh=True)
        payload: dict[str, object] = {
            "taskId": task_id,
            "status": job_status,
        }

        game_id = _extract_game_id(job)
        if game_id is not None:
            payload["gameId"] = game_id

        if job_status == "finished" and game_id is not None:
            game = get_object_or_404(Game, pk=game_id)
            payload["game"] = GameStateSerializer(game).data
        elif job_status == "failed":
            payload["error"] = "AI task failed."

        return Response(payload)


def _extract_game_id(job: Job) -> str | None:
    if isinstance(job.result, dict):
        game_id = job.result.get("game_id")
        if isinstance(game_id, str):
            return game_id

    if job.args and isinstance(job.args[0], str):
        return job.args[0]

    return None
