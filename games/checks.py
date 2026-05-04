from __future__ import annotations

import os

from django.core.checks import Error, Warning, register

from .services.ai.handler import DEFAULT_AI_BACKEND, DEFAULT_AI_MODEL, get_primary_provider


@register()
def check_primary_ai_provider(app_configs, **kwargs):
    try:
        provider = get_primary_provider(backend=DEFAULT_AI_BACKEND, model=DEFAULT_AI_MODEL)
    except ValueError as exc:
        return [
            Error(
                str(exc),
                hint="Set CHECKERS_AI_BACKEND to one of: gemini, openrouter, groq.",
                id="games.E001",
            )
        ]

    if provider.is_available():
        return []

    issue_class = Error if _fail_fast_enabled() else Warning
    issue_id = "games.E002" if _fail_fast_enabled() else "games.W001"
    return [
        issue_class(
            (
                f"Primary AI provider '{provider.provider_name}' is unavailable for "
                f"CHECKERS_AI_BACKEND='{DEFAULT_AI_BACKEND}'."
            ),
            hint=(
                "Configure the provider credentials before deploy, or choose a different "
                "backend. Set CHECKERS_AI_FAIL_FAST=true to make this a hard error."
            ),
            id=issue_id,
        )
    ]


def _fail_fast_enabled() -> bool:
    return (os.environ.get("CHECKERS_AI_FAIL_FAST") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
