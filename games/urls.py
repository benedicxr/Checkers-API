from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import GameViewSet, TaskStatusView

router = DefaultRouter()
router.register("games", GameViewSet, basename="game")

urlpatterns = [
    *router.urls,
    path("tasks/<str:task_id>/", TaskStatusView.as_view(), name="task-status"),
]
