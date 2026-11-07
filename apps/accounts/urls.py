"""Account URLs."""

from django.urls import path

from . import views

urlpatterns = [
    path("settings/", views.settings_view, name="settings"),
    path(
        "settings/password/",
        views.PasswordChangeView.as_view(),
        name="password_change",
    ),
]
