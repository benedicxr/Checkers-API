from __future__ import annotations

from ..base import BaseProvider, BoardState, IndexedMoves


class FirstLegalMoveProvider(BaseProvider):
    provider_name = "FirstLegalMoveProvider"

    def __init__(self):
        super().__init__(model="first-legal-move")

    def is_available(self) -> bool:
        return True

    def request_move_index(
        self,
        *,
        board_state: BoardState,
        indexed_moves: IndexedMoves,
    ) -> str:
        return '{"index": 0}'
