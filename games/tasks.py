from __future__ import annotations

from django_rq import job

from .models import Game
from .services import orchestrator


@job("default")
def process_ai_turn_task(game_id: str) -> dict[str, str]:
    game = orchestrator.handle_ai_turn(game_id)
    return {
        "game_id": str(game.pk),
        "status": game.status,
        "current_turn": game.current_turn,
    }
