from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import Game, MoveEntry


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


class GameStateSerializer(serializers.ModelSerializer):
    board = serializers.SerializerMethodField()
    currentTurn = serializers.CharField(source="current_turn")
    moveCount = serializers.IntegerField(source="move_count")
    createdAt = serializers.DateTimeField(source="created_at")
    updatedAt = serializers.DateTimeField(source="updated_at")

    class Meta:
        model = Game
        fields = (
            "id",
            "board",
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
