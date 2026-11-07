"""Workout runner, unscheduled session, tag, and history routes."""

from django.urls import path

from . import views

urlpatterns = [
    path("history/", views.history_view, name="history"),
    path("settings/tags/new/", views.tag_new, name="tag_new"),
    path("settings/tags/<int:pk>/edit/", views.tag_edit, name="tag_edit"),
    path("settings/tags/<int:pk>/delete/", views.tag_delete, name="tag_delete"),
    path("schedule/<int:pk>/start/", views.scheduled_start, name="scheduled_start"),
    path("sessions/new/", views.session_new, name="session_new"),
    path("sessions/log/", views.session_log, name="session_log"),
    path("sessions/<int:pk>/", views.session_detail, name="session_detail"),
    path("sessions/<int:pk>/edit/", views.session_edit, name="session_edit"),
    path("sessions/<int:pk>/delete/", views.session_delete, name="session_delete"),
    path("sessions/<int:pk>/run/", views.session_run, name="session_run"),
    path("sessions/<int:pk>/sets/", views.session_log_set, name="session_log_set"),
    path("sessions/<int:pk>/sets/add/", views.set_add, name="set_add"),
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
    path("sets/<int:pk>/row/", views.set_row, name="set_row"),
    path("sets/<int:pk>/edit/", views.set_edit, name="set_edit"),
    path("sets/<int:pk>/delete/", views.set_delete, name="set_delete"),
]
