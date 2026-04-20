from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .serializers import GameStateSerializer
from .services.exceptions import GameErrorCode
from .services.orchestrator import OrchestratorRuleError

RULE_ERROR_STATUS_CODES = {
    GameErrorCode.GAME_FINISHED: status.HTTP_409_CONFLICT,
    GameErrorCode.NO_MOVES_TO_UNDO: status.HTTP_409_CONFLICT,
    GameErrorCode.INVALID_BOARD_STATE: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response

    if isinstance(exc, OrchestratorRuleError):
        payload = {
            "error": {
                "code": exc.error.code,
                "detail": exc.error.detail,
            }
        }
        if exc.game is not None:
            payload["game"] = GameStateSerializer(exc.game).data
        return Response(payload, status=_status_code_for_rule_error(exc.error.code))

    return None


def _status_code_for_rule_error(error_code: GameErrorCode) -> int:
    return RULE_ERROR_STATUS_CODES.get(error_code, status.HTTP_400_BAD_REQUEST)
