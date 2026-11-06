"""Exercise library routes."""

from django.urls import path

from . import views

urlpatterns = [
    path("library/", views.library, name="library"),
    path("library/new/", views.create, name="exercise_new"),
    path("library/<int:pk>/", views.detail, name="exercise_detail"),
    path("library/<int:pk>/edit/", views.edit, name="exercise_edit"),
    path("library/<int:pk>/archive/", views.archive, name="exercise_archive"),
    path("library/<int:pk>/restore/", views.restore, name="exercise_restore"),
]
