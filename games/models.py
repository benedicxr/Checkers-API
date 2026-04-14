import uuid

from django.db import models
from django.utils import timezone


class Game(models.Model):
    class Turn(models.TextChoices):
        WHITE = "white", "White"
        BLACK = "black", "Black"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    board = models.JSONField()
    current_turn = models.CharField(max_length=10, choices=Turn.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    winner = models.CharField(max_length=10, choices=Turn.choices, null=True, blank=True)
    move_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    white_time_remaining = models.IntegerField(default=300)
    black_time_remaining = models.IntegerField(default=300)
    last_turn_started_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Game {self.id} ({self.status})"


class MoveEntry(models.Model):
    game = models.ForeignKey(Game, related_name="moves", on_delete=models.CASCADE)
    player_side = models.CharField(max_length=10, choices=Game.Turn.choices)
    from_pos = models.JSONField()
    to_pos = models.JSONField()
    is_jump = models.BooleanField(default=False)
    captured_pos = models.JSONField(null=True, blank=True)
    is_promoted = models.BooleanField(default=False)
    board_before = models.JSONField()
    white_time_before = models.PositiveIntegerField()
    black_time_before = models.PositiveIntegerField()
    last_turn_started_at_before = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.player_side}: {self.from_pos} -> {self.to_pos}"
