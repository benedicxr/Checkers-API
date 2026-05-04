from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TypedDict

from ..types import Coords, Move, Player


class AIPiecePayload(TypedDict):
    id: int
    color: Player
    is_king: bool


class AICoordsPayload(TypedDict):
    row: int
    col: int


AIMoveIndexPayload = TypedDict(
    "AIMoveIndexPayload",
    {
        "index": int,
        "from": AICoordsPayload,
        "to": AICoordsPayload,
        "type": str,
        "captured": AICoordsPayload | None,
        "path": list[AICoordsPayload],
        "captured_positions": list[AICoordsPayload],
    },
)


BoardState = list[list[AIPiecePayload | None]]
IndexedMoves = list[AIMoveIndexPayload]


class ProviderError(Exception):
    def __init__(self, message: str, *, provider_name: str):
        super().__init__(message)
        self.provider_name = provider_name


class ProviderNotConfigured(ProviderError):
    pass


class ProviderRequestFailed(ProviderError):
    pass


class ProviderInvalidResponse(ProviderError):
    pass


class BaseProvider(ABC):
    provider_name = "base"

    def __init__(self, *, model: str):
        self.model = model

    def get_best_move(
        self,
        board_state: BoardState,
        allowed_moves: list[Move],
    ) -> Move:
        if not allowed_moves:
            raise ValueError("allowed_moves must contain at least one move.")

        if not self.is_available():
            raise ProviderNotConfigured(
                f"{self.provider_name} is not configured or unavailable.",
                provider_name=self.provider_name,
            )

        indexed_moves = self._index_moves(allowed_moves)

        try:
            raw_content = self.request_move_index(
                board_state=board_state,
                indexed_moves=indexed_moves,
            )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderRequestFailed(
                f"{self.provider_name} request failed.",
                provider_name=self.provider_name,
            ) from exc

        move_index = self.extract_index(
            raw_content,
            len(allowed_moves),
            provider_name=self.provider_name,
        )

        return allowed_moves[move_index]

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def request_move_index(
        self,
        *,
        board_state: BoardState,
        indexed_moves: IndexedMoves,
    ) -> str | None:
        raise NotImplementedError

    def build_prompt(
        self,
        *,
        board_state: BoardState,
        indexed_moves: IndexedMoves,
    ) -> str:
        return (
            "You are a professional checkers player.\n"
            "Choose the strongest move from the provided legal moves.\n"
            "Return a JSON object only.\n"
            'The response format must be exactly: {"index": <integer>}.\n'
            "Do not add explanations, markdown, or extra text.\n\n"
            "Current board state JSON:\n"
            f"{json.dumps(board_state, ensure_ascii=True)}\n\n"
            "Legal moves JSON:\n"
            f"{json.dumps(indexed_moves, ensure_ascii=True)}\n\n"
            'Return only JSON like {"index": 0}.'
        )

    @staticmethod
    def extract_index(
        raw_content: str | None,
        total_moves: int,
        *,
        provider_name: str,
    ) -> int:
        if raw_content is None:
            raise ProviderInvalidResponse(
                "Provider response was empty.",
                provider_name=provider_name,
            )

        candidate = raw_content.strip()
        if not candidate:
            raise ProviderInvalidResponse(
                "Provider response was blank.",
                provider_name=provider_name,
            )

        json_candidate = _strip_code_fences(candidate)
        parsed_index = _extract_index_from_json(json_candidate)
        if parsed_index is not None:
            if 0 <= parsed_index < total_moves:
                return parsed_index
            raise ProviderInvalidResponse(
                f"Provider returned out-of-range index {parsed_index}.",
                provider_name=provider_name,
            )

        try:
            index = int(candidate)
        except ValueError:
            parsed_index = _extract_index_from_text(candidate)
            if parsed_index is None:
                raise ProviderInvalidResponse(
                    "Provider response did not contain a parseable move index.",
                    provider_name=provider_name,
                )
            index = parsed_index

        if 0 <= index < total_moves:
            return index
        raise ProviderInvalidResponse(
            f"Provider returned out-of-range index {index}.",
            provider_name=provider_name,
        )

    @staticmethod
    def _index_moves(allowed_moves: list[Move]) -> IndexedMoves:
        return [
            {
                "index": index,
                "from": _coords_to_payload(move.from_),
                "to": _coords_to_payload(move.to),
                "type": move.type,
                "captured": None if move.captured is None else _coords_to_payload(move.captured),
                "path": [_coords_to_payload(coords) for coords in (move.path or (move.from_, move.to))],
                "captured_positions": [
                    _coords_to_payload(coords)
                    for coords in (move.captured_positions or (() if move.captured is None else (move.captured,)))
                ],
            }
            for index, move in enumerate(allowed_moves)
        ]


def _coords_to_payload(coords: Coords) -> AICoordsPayload:
    return {"row": coords.r, "col": coords.c}


def _strip_code_fences(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped

    if lines[-1].strip() != "```":
        return stripped

    return "\n".join(lines[1:-1]).strip()


def _extract_index_from_json(content: str) -> int | None:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    index = payload.get("index")
    return index if isinstance(index, int) else None


def _extract_index_from_text(content: str) -> int | None:
    digits: list[str] = []
    collecting = False

    for char in content:
        if char.isdigit():
            digits.append(char)
            collecting = True
            continue

        if collecting:
            break

    if not digits:
        return None

    return int("".join(digits))
