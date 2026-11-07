"""Core routes: Today, health check, manifest, and milestone placeholders."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.today, name="today"),
    path(
        "stats/",
        views.placeholder,
        {
            "title": "Stats",
            "icon_name": "chart-line",
            "message": "Progress charts are coming in a later milestone.",
        },
        name="stats",
    ),
]
