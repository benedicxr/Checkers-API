from __future__ import annotations

import os

try:
    from groq import Groq
except ImportError:
    Groq = None

from ..base import BaseProvider, BoardState, IndexedMoves


class GroqProvider(BaseProvider):
    provider_name = "GroqProvider"

    def __init__(self, *, model: str):
        super().__init__(model=_normalize_groq_model_name(model))
        api_key = (os.environ.get("GROQ_API_KEY") or "").strip()
        self._client = Groq(api_key=api_key) if Groq is not None and api_key else None

    def is_available(self) -> bool:
        return self._client is not None

    def request_move_index(
        self,
        *,
        board_state: BoardState,
        indexed_moves: IndexedMoves,
    ) -> str | None:
        if self._client is None:
            return None

        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": 'Return only a JSON object in the form {"index": <integer>}.',
                },
                {
                    "role": "user",
                    "content": self.build_prompt(
                        board_state=board_state,
                        indexed_moves=indexed_moves,
                    ),
                }
            ],
            temperature=0,
        )
        return _extract_groq_text(response)


def _normalize_groq_model_name(model: str) -> str:
    if ":" in model:
        provider, _, model_name = model.partition(":")
        if provider.strip().lower() == "groq" and model_name:
            return model_name
    return model


def _extract_groq_text(response_payload: object) -> str | None:
    if response_payload is None:
        return None

    choices = getattr(response_payload, "choices", None)
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if message is None:
        return None

    content = getattr(message, "content", None)
    return content if isinstance(content, str) else None
