from django.urls import path

from .views import fetch_game, initialize_game, moves, restart_game, undo_move

urlpatterns = [
    path("games/", initialize_game, name="game-list"),
    path("games/<uuid:game_id>/", fetch_game, name="game-detail"),
    path("games/<uuid:game_id>/moves/", moves, name="game-moves"),
    path("games/<uuid:game_id>/undo/", undo_move, name="game-undo"),
    path("games/<uuid:game_id>/restart/", restart_game, name="game-restart"),
]
