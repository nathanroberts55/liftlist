"""Views for the app shell, health check, and PWA manifest."""

import logging

from django.contrib.auth.decorators import login_not_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.plans.services.today import build_today

logger = logging.getLogger(__name__)


@login_not_required
@never_cache
def healthz(request):
    """Liveness/readiness probe: confirms the database is reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check failed")
        return JsonResponse(
            {"status": "error", "database": "unavailable"},
            status=503,
        )
    return JsonResponse({"status": "ok", "database": "ok"})


@login_not_required
@never_cache
def manifest(request):
    """Web app manifest (F-12). Public so the browser can install the app."""
    icons = [
        {
            "src": static("img/icons/icon-192.png"),
            "sizes": "192x192",
            "type": "image/png",
            "purpose": "any",
        },
        {
            "src": static("img/icons/icon-512.png"),
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "any",
        },
        {
            "src": static("img/icons/icon-512-maskable.png"),
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "maskable",
        },
    ]
    data = {
        "id": "/",
        "name": "Lift List",
        "short_name": "Lift List",
        "description": "Plan workout splits, run workouts set by set, and track progress.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#0B0D10",
        "theme_color": "#0B0D10",
        "lang": "en",
        "dir": "ltr",
        "categories": ["health", "fitness", "sports"],
        "icons": icons,
    }
    return JsonResponse(data, content_type="application/manifest+json")


def today(request):
    """Today screen: active plan, today's workout, catch-up, and week strip."""
    today_date = timezone.localdate()
    context = build_today(request.user, today_date)
    context.update(
        {
            "page_title": "Today",
            "today": today_date,
        }
    )
    return render(request, "core/today.html", context)


def placeholder(request, *, title, icon_name, message):
    """Shared placeholder for destinations built in later milestones."""
    return render(
        request,
        "core/placeholder.html",
        {
            "page_title": title,
            "title": title,
            "icon_name": icon_name,
            "message": message,
        },
    )
