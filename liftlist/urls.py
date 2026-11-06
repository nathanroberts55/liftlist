"""URL configuration for Lift List."""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", core_views.healthz, name="healthz"),
    path("manifest.webmanifest", core_views.manifest, name="manifest"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,
            extra_context={"page_title": "Log in"},
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.exercises.urls")),
    path("", include("apps.plans.urls")),
    path("", include("apps.workouts.urls")),
    path("", include("apps.core.urls")),
]
