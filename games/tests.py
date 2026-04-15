from __future__ import annotations

import json

from django.test import TestCase
from django.urls import reverse

from .models import Game
from .services.board import create_initial_board
from .services.serialization import serialize_board
from .services.types import BLACK_PLAYER, Board, Piece, WHITE_PLAYER


def empty_board() -> Board:
    return [[None for _ in range(8)] for _ in range(8)]


class GameApiTests(TestCase):
    def post_json(self, url: str, payload: dict | None = None):
        return self.client.post(
            url,
            data=json.dumps(payload or {}),
            content_type="application/json",
        )

    def create_game(
        self,
        *,
        board: Board | None = None,
        current_turn: str = WHITE_PLAYER,
        status_value: str = Game.Status.ACTIVE,
        winner: str | None = None,
        move_count: int = 0,
    ) -> Game:
        if board is None:
            board = create_initial_board()

        return Game.objects.create(
            board=serialize_board(board),
            current_turn=current_turn,
            status=status_value,
            winner=winner,
            move_count=move_count,
        )

    def test_create_game_returns_initial_state(self):
        response = self.post_json(reverse("game-list"))

        self.assertEqual(response.status_code, 201)
        payload = response.json()

        self.assertEqual(payload["currentTurn"], WHITE_PLAYER)
        self.assertEqual(payload["status"], Game.Status.ACTIVE)
        self.assertIsNone(payload["winner"])
        self.assertEqual(payload["moveCount"], 0)

        white_pieces = 0
        black_pieces = 0
        for row in payload["board"]:
            for piece in row:
                if piece is None:
                    continue
                if piece["color"] == WHITE_PLAYER:
                    white_pieces += 1
                if piece["color"] == BLACK_PLAYER:
                    black_pieces += 1

        self.assertEqual(white_pieces, 12)
        self.assertEqual(black_pieces, 12)

    def test_move_applies_simple_move_and_records_history(self):
        game = self.create_game()

        response = self.post_json(
            reverse("game-move", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 4, "col": 1},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["currentTurn"], BLACK_PLAYER)
        self.assertEqual(payload["moveCount"], 1)
        self.assertIsNone(payload["board"][5][0])
        self.assertEqual(payload["board"][4][1]["color"], WHITE_PLAYER)

        history_response = self.client.get(reverse("game-moves", args=[game.id]))
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual(len(history_payload), 1)
        self.assertEqual(history_payload[0]["playerSide"], WHITE_PLAYER)
        self.assertEqual(history_payload[0]["fromPos"], {"row": 5, "col": 0})
        self.assertEqual(history_payload[0]["toPos"], {"row": 4, "col": 1})
        self.assertFalse(history_payload[0]["isJump"])

    def test_move_requires_capture_when_available(self):
        board = empty_board()
        board[5][0] = Piece(id=1, color=WHITE_PLAYER)
        board[5][4] = Piece(id=2, color=WHITE_PLAYER)
        board[4][1] = Piece(id=3, color=BLACK_PLAYER)
        game = self.create_game(board=board)

        response = self.post_json(
            reverse("game-move", args=[game.id]),
            {
                "from": {"row": 5, "col": 4},
                "to": {"row": 4, "col": 5},
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "mandatory_capture")

    def test_capture_chain_must_continue_with_same_piece(self):
        board = empty_board()
        board[5][0] = Piece(id=1, color=WHITE_PLAYER)
        board[5][4] = Piece(id=2, color=WHITE_PLAYER)
        board[4][1] = Piece(id=3, color=BLACK_PLAYER)
        board[2][3] = Piece(id=4, color=BLACK_PLAYER)
        game = self.create_game(board=board)

        first_capture = self.post_json(
            reverse("game-move", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 3, "col": 2},
            },
        )

        self.assertEqual(first_capture.status_code, 200)
        first_payload = first_capture.json()
        self.assertEqual(first_payload["currentTurn"], WHITE_PLAYER)
        self.assertEqual(first_payload["moveCount"], 1)
        self.assertIsNone(first_payload["board"][4][1])

        wrong_piece_response = self.post_json(
            reverse("game-move", args=[game.id]),
            {
                "from": {"row": 5, "col": 4},
                "to": {"row": 4, "col": 5},
            },
        )

        self.assertEqual(wrong_piece_response.status_code, 400)
        wrong_piece_payload = wrong_piece_response.json()
        self.assertEqual(wrong_piece_payload["error"]["code"], "capture_continuation_required")
        self.assertEqual(wrong_piece_payload["error"]["requiredFrom"], {"row": 3, "col": 2})

        second_capture = self.post_json(
            reverse("game-move", args=[game.id]),
            {
                "from": {"row": 3, "col": 2},
                "to": {"row": 1, "col": 4},
            },
        )

        self.assertEqual(second_capture.status_code, 200)
        second_payload = second_capture.json()
        self.assertEqual(second_payload["status"], Game.Status.FINISHED)
        self.assertEqual(second_payload["winner"], WHITE_PLAYER)
        self.assertEqual(second_payload["moveCount"], 2)

    def test_undo_restores_previous_board_snapshot(self):
        game = self.create_game()

        move_response = self.post_json(
            reverse("game-move", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 4, "col": 1},
            },
        )
        self.assertEqual(move_response.status_code, 200)

        undo_response = self.post_json(reverse("game-undo", args=[game.id]))

        self.assertEqual(undo_response.status_code, 200)
        undo_payload = undo_response.json()
        self.assertEqual(undo_payload["currentTurn"], WHITE_PLAYER)
        self.assertEqual(undo_payload["moveCount"], 0)
        self.assertIsNotNone(undo_payload["board"][5][0])
        self.assertIsNone(undo_payload["board"][4][1])

        history_response = self.client.get(reverse("game-moves", args=[game.id]))
        self.assertEqual(history_response.json(), [])

    def test_restart_resets_state_and_clears_history(self):
        game = self.create_game()
        self.post_json(
            reverse("game-move", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 4, "col": 1},
            },
        )

        restart_response = self.post_json(reverse("game-restart", args=[game.id]))

        self.assertEqual(restart_response.status_code, 200)
        restart_payload = restart_response.json()
        self.assertEqual(restart_payload["currentTurn"], WHITE_PLAYER)
        self.assertEqual(restart_payload["status"], Game.Status.ACTIVE)
        self.assertEqual(restart_payload["moveCount"], 0)

        history_response = self.client.get(reverse("game-moves", args=[game.id]))
        self.assertEqual(history_response.json(), [])
