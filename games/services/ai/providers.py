from __future__ import annotations

import json
import os
from urllib import error, request

try:
    from google import genai
except ImportError:
    genai = None

try:
    from groq import Groq
except ImportError:
    Groq = None

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
        if self._client is None:
            return None

        response = self._client.models.generate_content(
            model=self.model,
            contents=self.build_prompt(board_state=board_state, indexed_moves=indexed_moves),
        )
        return getattr(response, "text", None)


class OpenRouterMoveSelector(BaseMoveSelector):
    provider_name = "OpenRouterMoveSelector"
    _api_url = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, *, model: str):
        super().__init__(model=_normalize_openrouter_model_name(model))
        self._api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        self._site_url = (os.environ.get("OPENROUTER_SITE_URL") or "").strip()
        self._site_name = (os.environ.get("OPENROUTER_SITE_NAME") or "").strip()

    def is_available(self) -> bool:
        return bool(self._api_key)

    def request_move_index(
        self,
        *,
        board_state: BoardState,
        indexed_moves: IndexedMoves,
    ) -> str | None:
        if not self._api_key:
            return None

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": self.build_prompt(
                            board_state=board_state,
                            indexed_moves=indexed_moves,
                        ),
                    }
                ],
            }
        ).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._site_name:
            headers["X-Title"] = self._site_name

        http_request = request.Request(
            self._api_url,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=30) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError:
            return None
        except error.URLError:
            return None
        except TimeoutError:
            return None
        except json.JSONDecodeError:
            return None

        return _extract_openrouter_text(response_payload)


class GroqMoveSelector(BaseMoveSelector):
    provider_name = "GroqMoveSelector"

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


def _normalize_gemini_model_name(model: str) -> str:
    if ":" in model:
        provider, _, model_name = model.partition(":")
        if provider.strip().lower() == "google" and model_name:
            return model_name
    return model


def _normalize_openrouter_model_name(model: str) -> str:
    if ":" in model:
        provider, _, model_name = model.partition(":")
        if provider.strip().lower() == "openrouter" and model_name:
            return model_name
    return model


def _normalize_groq_model_name(model: str) -> str:
    if ":" in model:
        provider, _, model_name = model.partition(":")
        if provider.strip().lower() == "groq" and model_name:
            return model_name
    return model


def _extract_openrouter_text(response_payload: object) -> str | None:
    return _extract_chat_completion_text(response_payload, provider_name="OpenRouter")


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
    if isinstance(content, str):
        return content

    return None


def _extract_chat_completion_text(response_payload: object, *, provider_name: str) -> str | None:
    if not isinstance(response_payload, dict):
        return None

    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None

    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None

    content = message.get("content")
    if isinstance(content, str):
        return content

    return None
