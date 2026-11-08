"""Stats tabs and Chart.js JSON endpoints (F-10)."""

from django.urls import path

from . import views

urlpatterns = [
    path("stats/", views.stats_home, name="stats"),
    path("stats/api/top-set/", views.api_top_set, name="stats_api_top_set"),
    path("stats/api/volume/", views.api_volume, name="stats_api_volume"),
]
