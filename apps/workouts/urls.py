"""Workout runner routes (F-05)."""

from django.urls import path

from . import views

urlpatterns = [
    path("schedule/<int:pk>/start/", views.scheduled_start, name="scheduled_start"),
    path("sessions/<int:pk>/run/", views.session_run, name="session_run"),
    path("sessions/<int:pk>/sets/", views.session_log_set, name="session_log_set"),
    path("sessions/<int:pk>/skip-set/", views.session_skip_set, name="session_skip_set"),
    path("sessions/<int:pk>/add-set/", views.session_add_set, name="session_add_set"),
    path(
        "sessions/<int:pk>/skip-exercise/",
        views.session_skip_exercise,
        name="session_skip_exercise",
    ),
    path(
        "sessions/<int:pk>/add-exercise/",
        views.session_add_exercise,
        name="session_add_exercise",
    ),
    path("sessions/<int:pk>/reorder/", views.session_reorder, name="session_reorder"),
    path(
        "sessions/<int:pk>/move-exercise/",
        views.session_move_exercise,
        name="session_move_exercise",
    ),
    path(
        "sessions/<int:pk>/jump/<int:exercise_id>/",
        views.session_jump,
        name="session_jump",
    ),
    path("sessions/<int:pk>/picker/", views.session_picker, name="session_picker"),
    path("sessions/<int:pk>/finish/", views.session_finish, name="session_finish"),
    path("sessions/<int:pk>/discard/", views.session_discard, name="session_discard"),
]
