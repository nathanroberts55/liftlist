"""Core routes: Today and the app-shell placeholder helper."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.today, name="today"),
]
