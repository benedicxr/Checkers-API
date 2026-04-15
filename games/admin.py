from django.contrib import admin

from .models import Game, MoveEntry


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("id", "current_turn", "status", "winner", "move_count", "updated_at")
    list_filter = ("status", "current_turn", "winner")
    readonly_fields = ("created_at", "updated_at")
    search_fields = ("id",)


@admin.register(MoveEntry)
class MoveEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "game", "player_side", "from_pos", "to_pos", "is_jump", "is_promoted", "created_at")
    list_filter = ("player_side", "is_jump", "is_promoted")
    readonly_fields = ("created_at",)
