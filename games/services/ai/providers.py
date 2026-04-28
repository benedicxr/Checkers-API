from __future__ import annotations

import os

try:
    from google import genai
except ImportError:
    genai = None

from .base import BaseMoveSelector, BoardState, IndexedMoves


class GeminiMoveSelector(BaseMoveSelector):
    provider_name = "GeminiMoveSelector"

    def __init__(self, *, model: str):
        super().__init__(model=_normalize_gemini_model_name(model))
        api_key = (os.environ.get("GOOGLE_API_KEY") or "").strip()
        self._client = genai.Client(api_key=api_key) if genai is not None and api_key else None

    def is_available(self) -> bool:
        return self._client is not None

    def request_move_index(
        self,
        *,
        board_state: BoardState,
        indexed_moves: IndexedMoves,
    ) -> str | None:
        response = self._client.models.generate_content(
            model=self.model,
            contents=self.build_prompt(board_state=board_state, indexed_moves=indexed_moves),
        )
        return getattr(response, "text", None)


def _normalize_gemini_model_name(model: str) -> str:
    if ":" in model:
        provider, _, model_name = model.partition(":")
        if provider.strip().lower() == "google" and model_name:
            return model_name
    return model
