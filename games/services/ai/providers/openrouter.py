from __future__ import annotations

import json
import os
from urllib import error, request

from ..base import BaseProvider, BoardState, IndexedMoves
from .common import extract_chat_completion_text


class OpenRouterProvider(BaseProvider):
    provider_name = "OpenRouterProvider"
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

        return extract_chat_completion_text(response_payload)


def _normalize_openrouter_model_name(model: str) -> str:
    if ":" in model:
        provider, _, model_name = model.partition(":")
        if provider.strip().lower() == "openrouter" and model_name:
            return model_name
    return model
