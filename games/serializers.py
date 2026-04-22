from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import Game, MoveEntry
from .services import orchestrator
from .services.types import Coords, Move


class PieceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    color = serializers.CharField()
    isKing = serializers.SerializerMethodField()

    def get_isKing(self, obj: dict[str, Any]) -> bool:
        return bool(obj.get("is_king", obj.get("isKing", False)))


class PositionSerializer(serializers.Serializer):
    row = serializers.IntegerField(min_value=0, max_value=7)
    col = serializers.IntegerField(min_value=0, max_value=7)


class MovePayloadSerializer(serializers.Serializer):
    from_pos = PositionSerializer()
    to_pos = PositionSerializer()

    def to_internal_value(self, data: Any) -> dict[str, dict[str, int]]:
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected a JSON object.")

        normalized_data = {
            "from_pos": data.get("from"),
            "to_pos": data.get("to"),
        }
        return super().to_internal_value(normalized_data)


class AllowedMoveSerializer(serializers.Serializer):
    fromPos = serializers.SerializerMethodField()
    toPos = serializers.SerializerMethodField()
    isCapture = serializers.SerializerMethodField()
    capturedPos = serializers.SerializerMethodField()

    def get_fromPos(self, obj: Move) -> dict[str, int]:
        return _coords_to_payload(obj.from_)

    def get_toPos(self, obj: Move) -> dict[str, int]:
        return _coords_to_payload(obj.to)

    def get_isCapture(self, obj: Move) -> bool:
        return obj.type == "capture"

    def get_capturedPos(self, obj: Move) -> dict[str, int] | None:
        if obj.captured is None:
            return None
        return _coords_to_payload(obj.captured)


class GameStateSerializer(serializers.ModelSerializer):
    board = serializers.SerializerMethodField()
    allowedMoves = serializers.SerializerMethodField()
    currentTurn = serializers.CharField(source="current_turn")
    moveCount = serializers.IntegerField(source="move_count")
    createdAt = serializers.DateTimeField(source="created_at")
    updatedAt = serializers.DateTimeField(source="updated_at")

    class Meta:
        model = Game
        fields = (
            "id",
            "board",
            "allowedMoves",
            "currentTurn",
            "status",
            "winner",
            "moveCount",
            "createdAt",
            "updatedAt",
        )
        read_only_fields = (
            "id",
            "board",
            "allowedMoves",
            "currentTurn",
            "status",
            "winner",
            "moveCount",
            "createdAt",
            "updatedAt",
        )

    def get_board(self, obj: Game) -> list[list[dict[str, Any] | None]]:
        serialized_board: list[list[dict[str, Any] | None]] = []
        for row in obj.board:
            serialized_row: list[dict[str, Any] | None] = []
            for piece in row:
                if piece is None:
                    serialized_row.append(None)
                else:
                    serialized_row.append(PieceSerializer(piece).data)
            serialized_board.append(serialized_row)
        return serialized_board

    def get_allowedMoves(self, obj: Game) -> list[dict[str, Any]]:
        return AllowedMoveSerializer(orchestrator.get_allowed_moves(obj), many=True).data


class MoveEntrySerializer(serializers.ModelSerializer):
    playerSide = serializers.CharField(source="player_side")
    fromPos = PositionSerializer(source="from_pos", read_only=True)
    toPos = PositionSerializer(source="to_pos", read_only=True)
    isJump = serializers.BooleanField(source="is_jump")
    capturedPos = serializers.SerializerMethodField()
    isPromoted = serializers.BooleanField(source="is_promoted")
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = MoveEntry
        fields = (
            "id",
            "playerSide",
            "fromPos",
            "toPos",
            "isJump",
            "capturedPos",
            "isPromoted",
            "createdAt",
        )

    def get_capturedPos(self, obj: MoveEntry) -> dict[str, int] | None:
        if obj.captured_pos is None:
            return None
        return PositionSerializer(obj.captured_pos).data


def _coords_to_payload(coords: Coords) -> dict[str, int]:
    return {"row": coords.r, "col": coords.c}
