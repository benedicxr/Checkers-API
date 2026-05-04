from __future__ import annotations

import json
from unittest.mock import MagicMock
from unittest.mock import patch

from django.core.checks import Error, Warning
from django.test import TestCase
from django.urls import reverse

from .models import Game
from .checks import check_primary_ai_provider
from .services.ai import BaseProvider, CheckersAIHandler, ProviderNotConfigured, ProviderRequestFailed
from .services.ai.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    InMemoryCircuitBreakerStore,
)
from .services.ai.handler import build_provider_chain, get_primary_provider
from .services.ai.providers import FirstLegalMoveProvider
from .services.board import create_initial_board
from .services.exceptions import GameErrorCode
from .services.serialization import serialize_board
from .services.types import BLACK_PLAYER, Board, Coords, Move, Piece, WHITE_PLAYER


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
        mode: str = Game.Mode.PVP,
        current_turn: str = WHITE_PLAYER,
        status_value: str = Game.Status.ACTIVE,
        winner: str | None = None,
        move_count: int = 0,
    ) -> Game:
        if board is None:
            board = create_initial_board()

        return Game.objects.create(
            mode=mode,
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

        self.assertEqual(payload["mode"], Game.Mode.VS_AI)
        self.assertEqual(payload["currentTurn"], WHITE_PLAYER)
        self.assertEqual(payload["status"], Game.Status.ACTIVE)
        self.assertIsNone(payload["winner"])
        self.assertEqual(payload["moveCount"], 0)
        self.assertEqual(
            payload["allowedMoves"],
            [
                {
                    "fromPos": {"row": 5, "col": 0},
                    "toPos": {"row": 4, "col": 1},
                    "isCapture": False,
                    "capturedPos": None,
                    "path": [{"row": 5, "col": 0}, {"row": 4, "col": 1}],
                    "capturedPositions": [],
                },
                {
                    "fromPos": {"row": 5, "col": 2},
                    "toPos": {"row": 4, "col": 1},
                    "isCapture": False,
                    "capturedPos": None,
                    "path": [{"row": 5, "col": 2}, {"row": 4, "col": 1}],
                    "capturedPositions": [],
                },
                {
                    "fromPos": {"row": 5, "col": 2},
                    "toPos": {"row": 4, "col": 3},
                    "isCapture": False,
                    "capturedPos": None,
                    "path": [{"row": 5, "col": 2}, {"row": 4, "col": 3}],
                    "capturedPositions": [],
                },
                {
                    "fromPos": {"row": 5, "col": 4},
                    "toPos": {"row": 4, "col": 3},
                    "isCapture": False,
                    "capturedPos": None,
                    "path": [{"row": 5, "col": 4}, {"row": 4, "col": 3}],
                    "capturedPositions": [],
                },
                {
                    "fromPos": {"row": 5, "col": 4},
                    "toPos": {"row": 4, "col": 5},
                    "isCapture": False,
                    "capturedPos": None,
                    "path": [{"row": 5, "col": 4}, {"row": 4, "col": 5}],
                    "capturedPositions": [],
                },
                {
                    "fromPos": {"row": 5, "col": 6},
                    "toPos": {"row": 4, "col": 5},
                    "isCapture": False,
                    "capturedPos": None,
                    "path": [{"row": 5, "col": 6}, {"row": 4, "col": 5}],
                    "capturedPositions": [],
                },
                {
                    "fromPos": {"row": 5, "col": 6},
                    "toPos": {"row": 4, "col": 7},
                    "isCapture": False,
                    "capturedPos": None,
                    "path": [{"row": 5, "col": 6}, {"row": 4, "col": 7}],
                    "capturedPositions": [],
                },
            ],
        )

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
            reverse("game-moves", args=[game.id]),
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
        self.assertIsNotNone(payload["board"][2][1])
        self.assertIsNone(payload["board"][3][0])

        history_response = self.client.get(reverse("game-moves", args=[game.id]))
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual(len(history_payload), 1)
        self.assertEqual(history_payload[0]["playerSide"], WHITE_PLAYER)
        self.assertEqual(history_payload[0]["fromPos"], {"row": 5, "col": 0})
        self.assertEqual(history_payload[0]["toPos"], {"row": 4, "col": 1})
        self.assertFalse(history_payload[0]["isJump"])
        self.assertEqual(history_payload[0]["capturedPositions"], [])
        self.assertEqual(history_payload[0]["path"], [{"row": 5, "col": 0}, {"row": 4, "col": 1}])

    def test_move_requires_capture_when_available(self):
        board = empty_board()
        board[5][0] = Piece(id=1, color=WHITE_PLAYER)
        board[5][4] = Piece(id=2, color=WHITE_PLAYER)
        board[4][1] = Piece(id=3, color=BLACK_PLAYER)
        game = self.create_game(board=board)

        response = self.post_json(
            reverse("game-moves", args=[game.id]),
            {
                "from": {"row": 5, "col": 4},
                "to": {"row": 4, "col": 5},
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], GameErrorCode.MANDATORY_CAPTURE)

    def test_capture_chain_must_continue_with_same_piece(self):
        board = empty_board()
        board[5][0] = Piece(id=1, color=WHITE_PLAYER)
        board[5][4] = Piece(id=2, color=WHITE_PLAYER)
        board[4][1] = Piece(id=3, color=BLACK_PLAYER)
        board[2][3] = Piece(id=4, color=BLACK_PLAYER)
        game = self.create_game(board=board)

        first_capture = self.post_json(
            reverse("game-moves", args=[game.id]),
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
        self.assertEqual(
            first_payload["allowedMoves"],
            [
                {
                    "fromPos": {"row": 3, "col": 2},
                    "toPos": {"row": 1, "col": 4},
                    "isCapture": True,
                    "capturedPos": {"row": 2, "col": 3},
                    "path": [{"row": 3, "col": 2}, {"row": 1, "col": 4}],
                    "capturedPositions": [{"row": 2, "col": 3}],
                }
            ],
        )

        wrong_piece_response = self.post_json(
            reverse("game-moves", args=[game.id]),
            {
                "from": {"row": 5, "col": 4},
                "to": {"row": 4, "col": 5},
            },
        )

        self.assertEqual(wrong_piece_response.status_code, 400)
        wrong_piece_payload = wrong_piece_response.json()
        self.assertEqual(
            wrong_piece_payload["error"]["code"],
            GameErrorCode.CAPTURE_CONTINUATION_REQUIRED,
        )

        second_capture = self.post_json(
            reverse("game-moves", args=[game.id]),
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
        self.assertEqual(second_payload["allowedMoves"], [])

    def test_allowed_moves_include_full_multi_jump_path(self):
        board = empty_board()
        board[5][0] = Piece(id=1, color=WHITE_PLAYER)
        board[4][1] = Piece(id=2, color=BLACK_PLAYER)
        board[2][3] = Piece(id=3, color=BLACK_PLAYER)
        game = self.create_game(board=board)

        response = self.client.get(reverse("game-detail", args=[game.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["allowedMoves"],
            [
                {
                    "fromPos": {"row": 5, "col": 0},
                    "toPos": {"row": 1, "col": 4},
                    "isCapture": True,
                    "capturedPos": {"row": 4, "col": 1},
                    "path": [
                        {"row": 5, "col": 0},
                        {"row": 3, "col": 2},
                        {"row": 1, "col": 4},
                    ],
                    "capturedPositions": [
                        {"row": 4, "col": 1},
                        {"row": 2, "col": 3},
                    ],
                }
            ],
        )

        move_response = self.post_json(
            reverse("game-moves", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 1, "col": 4},
            },
        )

        self.assertEqual(move_response.status_code, 200)
        move_payload = move_response.json()
        self.assertIsNone(move_payload["board"][5][0])
        self.assertIsNone(move_payload["board"][4][1])
        self.assertIsNone(move_payload["board"][2][3])
        self.assertEqual(move_payload["board"][1][4]["color"], WHITE_PLAYER)

        history_response = self.client.get(reverse("game-moves", args=[game.id]))
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.json()
        self.assertEqual(len(history_payload), 1)
        self.assertEqual(history_payload[0]["capturedPos"], {"row": 4, "col": 1})
        self.assertEqual(
            history_payload[0]["capturedPositions"],
            [{"row": 4, "col": 1}, {"row": 2, "col": 3}],
        )
        self.assertEqual(
            history_payload[0]["path"],
            [
                {"row": 5, "col": 0},
                {"row": 3, "col": 2},
                {"row": 1, "col": 4},
            ],
        )

    def test_create_game_accepts_pvp_mode(self):
        response = self.post_json(reverse("game-list"), {"mode": Game.Mode.PVP})

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["mode"], Game.Mode.PVP)
        self.assertEqual(payload["currentTurn"], WHITE_PLAYER)
        self.assertEqual(payload["moveCount"], 0)

    def test_undo_restores_previous_player_decision_in_vs_ai_mode(self):
        board = empty_board()
        board[5][0] = Piece(id=1, color=WHITE_PLAYER)
        board[2][7] = Piece(id=2, color=BLACK_PLAYER)
        game = self.create_game(board=board, mode=Game.Mode.VS_AI)

        move_response = self.post_json(
            reverse("game-moves", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 4, "col": 1},
            },
        )
        self.assertEqual(move_response.status_code, 200)

        undo_response = self.post_json(reverse("game-undo", args=[game.id]))

        self.assertEqual(undo_response.status_code, 200)
        undo_payload = undo_response.json()
        self.assertEqual(undo_payload["mode"], Game.Mode.VS_AI)
        self.assertEqual(undo_payload["currentTurn"], WHITE_PLAYER)
        self.assertEqual(undo_payload["moveCount"], 0)
        self.assertIsNotNone(undo_payload["board"][5][0])
        self.assertIsNone(undo_payload["board"][4][1])
        self.assertIsNotNone(undo_payload["board"][2][7])
        self.assertIsNone(undo_payload["board"][3][6])

        history_response = self.client.get(reverse("game-moves", args=[game.id]))
        self.assertEqual(history_response.json(), [])

    @patch("games.services.orchestrator.CheckersAIHandler.get_best_move")
    def test_undo_reverts_single_ply_in_pvp_mode(self, mock_get_best_move):
        game = self.create_game(mode=Game.Mode.PVP)

        move_response = self.post_json(
            reverse("game-moves", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 4, "col": 1},
            },
        )
        self.assertEqual(move_response.status_code, 200)
        mock_get_best_move.assert_not_called()

        undo_response = self.post_json(reverse("game-undo", args=[game.id]))

        self.assertEqual(undo_response.status_code, 200)
        undo_payload = undo_response.json()
        self.assertEqual(undo_payload["mode"], Game.Mode.PVP)
        self.assertEqual(undo_payload["currentTurn"], WHITE_PLAYER)
        self.assertEqual(undo_payload["moveCount"], 0)
        self.assertIsNotNone(undo_payload["board"][5][0])
        self.assertIsNone(undo_payload["board"][4][1])

    @patch("games.services.orchestrator.CheckersAIHandler.get_best_move")
    def test_pvp_mode_does_not_trigger_ai_response(self, mock_get_best_move):
        game = self.create_game(mode=Game.Mode.PVP)

        response = self.post_json(
            reverse("game-moves", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 4, "col": 1},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], Game.Mode.PVP)
        self.assertEqual(payload["currentTurn"], BLACK_PLAYER)
        self.assertEqual(payload["moveCount"], 1)
        self.assertEqual(payload["board"][4][1]["color"], WHITE_PLAYER)
        self.assertIsNone(payload["board"][2][1])
        mock_get_best_move.assert_not_called()

    def test_restart_resets_state_and_clears_history(self):
        game = self.create_game()
        self.post_json(
            reverse("game-moves", args=[game.id]),
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

    def test_vs_ai_forced_reply_returns_200_immediately(self):
        board = empty_board()
        board[5][0] = Piece(id=1, color=WHITE_PLAYER)
        board[2][7] = Piece(id=2, color=BLACK_PLAYER)
        game = self.create_game(board=board, mode=Game.Mode.VS_AI)

        response = self.post_json(
            reverse("game-moves", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 4, "col": 1},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], Game.Mode.VS_AI)
        self.assertEqual(payload["currentTurn"], WHITE_PLAYER)
        self.assertEqual(payload["moveCount"], 2)
        self.assertEqual(payload["board"][4][1]["color"], WHITE_PLAYER)
        self.assertIsNone(payload["board"][2][7])
        self.assertEqual(payload["board"][3][6]["color"], BLACK_PLAYER)

    @patch("games.views.process_ai_turn_task.delay")
    def test_vs_ai_returns_202_and_task_id_when_ai_has_multiple_moves(self, mock_delay):
        game = self.create_game(mode=Game.Mode.VS_AI)
        mock_delay.return_value = MagicMock(id="task-123")

        response = self.post_json(
            reverse("game-moves", args=[game.id]),
            {
                "from": {"row": 5, "col": 0},
                "to": {"row": 4, "col": 1},
            },
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["taskId"], "task-123")
        self.assertEqual(payload["status"], "queued")
        self.assertEqual(payload["game"]["mode"], Game.Mode.VS_AI)
        self.assertEqual(payload["game"]["currentTurn"], BLACK_PLAYER)
        self.assertEqual(payload["game"]["moveCount"], 1)
        mock_delay.assert_called_once()

    @patch("games.views.Job.fetch")
    def test_task_status_returns_finished_game_state(self, mock_fetch):
        game = self.create_game(mode=Game.Mode.VS_AI)
        mock_job = MagicMock()
        mock_job.get_status.return_value = "finished"
        mock_job.result = {"game_id": str(game.id)}
        mock_job.args = [str(game.id)]
        mock_fetch.return_value = mock_job

        response = self.client.get(reverse("task-status", args=["task-123"]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["taskId"], "task-123")
        self.assertEqual(payload["status"], "finished")
        self.assertEqual(payload["gameId"], str(game.id))
        self.assertEqual(payload["game"]["id"], str(game.id))


class _UnavailableProvider(BaseProvider):
    provider_name = "UnavailableProvider"

    def is_available(self) -> bool:
        return False

    def request_move_index(self, *, board_state, indexed_moves):
        raise AssertionError("request_move_index should not be called")


class _FixedMoveProvider(BaseProvider):
    provider_name = "FixedMoveProvider"

    def __init__(self, *, model: str, raw_content: str):
        super().__init__(model=model)
        self.raw_content = raw_content

    def is_available(self) -> bool:
        return True

    def request_move_index(self, *, board_state, indexed_moves):
        return self.raw_content


class _FlakyProvider(BaseProvider):
    provider_name = "FlakyProvider"

    def __init__(self, *, model: str, failures_before_success: int):
        super().__init__(model=model)
        self.failures_before_success = failures_before_success
        self.call_count = 0

    def is_available(self) -> bool:
        return True

    def request_move_index(self, *, board_state, indexed_moves):
        self.call_count += 1
        if self.call_count <= self.failures_before_success:
            raise ProviderRequestFailed(
                "temporary upstream failure",
                provider_name=self.provider_name,
            )
        return '{"index": 1}'


class AIProviderTests(TestCase):
    def test_provider_raises_when_not_configured(self):
        provider = _UnavailableProvider(model="test")

        with self.assertRaises(ProviderNotConfigured):
            provider.get_best_move([], [Move(type="simple", from_=Coords(5, 0), to=Coords(4, 1))])

    @patch("games.services.ai.handler.logger")
    def test_handler_falls_through_to_next_provider(self, mock_logger):
        moves = [
            Move(type="simple", from_=Coords(5, 0), to=Coords(4, 1)),
            Move(type="simple", from_=Coords(5, 2), to=Coords(4, 3)),
        ]
        handler = CheckersAIHandler(
            providers=[
                _UnavailableProvider(model="missing"),
                _FixedMoveProvider(model="working", raw_content='{"index": 1}'),
            ]
        )

        selected_move = handler.get_best_move([], moves)

        self.assertEqual(selected_move, moves[1])
        self.assertEqual(mock_logger.warning.call_count, 2)

    @patch("games.services.ai.handler.logger")
    def test_handler_uses_terminal_fallback_provider(self, mock_logger):
        moves = [
            Move(type="simple", from_=Coords(5, 0), to=Coords(4, 1)),
            Move(type="simple", from_=Coords(5, 2), to=Coords(4, 3)),
        ]
        handler = CheckersAIHandler(
            providers=[
                _FixedMoveProvider(model="broken", raw_content='{"index": 99}'),
                FirstLegalMoveProvider(),
            ]
        )

        selected_move = handler.get_best_move([], moves)

        self.assertEqual(selected_move, moves[0])
        self.assertEqual(mock_logger.warning.call_count, 3)

    def test_build_provider_chain_appends_first_legal_fallback(self):
        providers = build_provider_chain(backend="gemini", model="gemini-2.5-flash")

        self.assertEqual(providers[-1].provider_name, "FirstLegalMoveProvider")

    def test_build_provider_chain_preserves_configured_provider_order(self):
        providers = build_provider_chain(backend="groq,gemini", model="test-model")

        self.assertEqual(
            [provider.provider_name for provider in providers],
            ["GroqProvider", "GeminiProvider", "FirstLegalMoveProvider"],
        )

    @patch.dict(
        "os.environ",
        {
            "CHECKERS_AI_MODEL_GROQ": "llama-3.1-8b-instant",
            "CHECKERS_AI_MODEL_GEMINI": "gemini-2.5-flash",
        },
        clear=False,
    )
    def test_build_provider_chain_uses_per_provider_models(self):
        providers = build_provider_chain(backend="groq,gemini", model="shared-model")

        self.assertEqual(
            [provider.model for provider in providers],
            ["llama-3.1-8b-instant", "gemini-2.5-flash", "first-legal-move"],
        )

    @patch.dict(
        "os.environ",
        {"CHECKERS_AI_MODEL_GEMINI": "gemini-2.5-flash"},
        clear=False,
    )
    def test_get_primary_provider_uses_provider_specific_model(self):
        provider = get_primary_provider(backend="gemini,groq", model="shared-model")

        self.assertEqual(provider.provider_name, "GeminiProvider")
        self.assertEqual(provider.model, "gemini-2.5-flash")

    def test_circuit_breaker_opens_after_repeated_provider_failures(self):
        provider = _FlakyProvider(model="flaky-model", failures_before_success=2)
        fallback = _FixedMoveProvider(model="fallback-model", raw_content='{"index": 0}')
        clock_value = [100.0]
        handler = CheckersAIHandler(
            providers=[provider, fallback],
            circuit_breaker=CircuitBreaker(
                store=InMemoryCircuitBreakerStore(),
                config=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=60),
                clock=lambda: clock_value[0],
            ),
        )
        moves = [
            Move(type="simple", from_=Coords(5, 0), to=Coords(4, 1)),
            Move(type="simple", from_=Coords(5, 2), to=Coords(4, 3)),
        ]

        first_move = handler.get_best_move([], moves)
        second_move = handler.get_best_move([], moves)
        third_move = handler.get_best_move([], moves)

        self.assertEqual(first_move, moves[0])
        self.assertEqual(second_move, moves[0])
        self.assertEqual(third_move, moves[0])
        self.assertEqual(provider.call_count, 2)

    def test_circuit_breaker_allows_half_open_recovery_after_timeout(self):
        provider = _FlakyProvider(model="recovering-model", failures_before_success=2)
        fallback = _FixedMoveProvider(model="fallback-model", raw_content='{"index": 0}')
        clock_value = [100.0]
        handler = CheckersAIHandler(
            providers=[provider, fallback],
            circuit_breaker=CircuitBreaker(
                store=InMemoryCircuitBreakerStore(),
                config=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=30),
                clock=lambda: clock_value[0],
            ),
        )
        moves = [
            Move(type="simple", from_=Coords(5, 0), to=Coords(4, 1)),
            Move(type="simple", from_=Coords(5, 2), to=Coords(4, 3)),
        ]

        handler.get_best_move([], moves)
        handler.get_best_move([], moves)
        skipped_move = handler.get_best_move([], moves)
        clock_value[0] = 131.0
        recovered_move = handler.get_best_move([], moves)

        self.assertEqual(skipped_move, moves[0])
        self.assertEqual(recovered_move, moves[1])
        self.assertEqual(provider.call_count, 3)


class AIStartupChecksTests(TestCase):
    @patch("games.checks.get_primary_provider")
    def test_startup_check_warns_when_primary_provider_is_unavailable(self, mock_get_primary_provider):
        provider = MagicMock()
        provider.provider_name = "GeminiProvider"
        provider.is_available.return_value = False
        mock_get_primary_provider.return_value = provider

        messages = check_primary_ai_provider(None)

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Warning)
        self.assertEqual(messages[0].id, "games.W001")

    @patch.dict("os.environ", {"CHECKERS_AI_FAIL_FAST": "true"}, clear=False)
    @patch("games.checks.get_primary_provider")
    def test_startup_check_can_fail_fast(self, mock_get_primary_provider):
        provider = MagicMock()
        provider.provider_name = "GeminiProvider"
        provider.is_available.return_value = False
        mock_get_primary_provider.return_value = provider

        messages = check_primary_ai_provider(None)

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, "games.E002")
