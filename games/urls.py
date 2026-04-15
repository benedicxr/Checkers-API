from django.urls import path

from .views import attempt_move, fetch_game, fetch_moves, initialize_game, restart_game, undo_move

urlpatterns = [
    path("games/", initialize_game, name="game-list"),
    path("games/<uuid:game_id>/", fetch_game, name="game-detail"),
    path("games/<uuid:game_id>/move/", attempt_move, name="game-move"),
    path("games/<uuid:game_id>/undo/", undo_move, name="game-undo"),
    path("games/<uuid:game_id>/restart/", restart_game, name="game-restart"),
    path("games/<uuid:game_id>/moves/", fetch_moves, name="game-moves"),
]
