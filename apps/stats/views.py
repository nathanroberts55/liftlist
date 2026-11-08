"""Stats tabs and the JSON endpoints that feed Chart.js (F-10)."""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.exercises.models import Exercise, MuscleGroup
from apps.plans.services import scheduling
from apps.workouts.services import tags as tag_services

from .services import aggregations

TABS = ("progress", "prs", "volume")
RANGE_KEYS = {key for key, _label in aggregations.RANGE_LABELS}


def _int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _range(raw):
    return raw if raw in RANGE_KEYS else "3m"


def _metric(raw):
    return raw if raw in ("sets", "tonnage") else "sets"


def _empty_chart(label="Top set (lb)"):
    return {
        "labels": [],
        "values": [],
        "tooltips": [],
        "label": label,
        "color_index": 0,
        "range": "3m",
        "exercise_id": None,
    }


@require_GET
def stats_home(request):
    """One page with Progress, PRs, and Volume tabs."""
    today = timezone.localdate()
    scheduling.sync_statuses(request.user, today)
    tab = request.GET.get("tab", "progress")
    if tab not in TABS:
        tab = "progress"

    context = {
        "page_title": "Stats",
        "tab": tab,
        "range_labels": aggregations.RANGE_LABELS,
        "range_key": _range(request.GET.get("range", "3m")),
        "muscles": MuscleGroup.objects.all(),
        "tags": tag_services.list_tags(request.user),
    }

    if tab == "progress":
        exercise = aggregations.exercise_with_history(
            request.user,
            preferred_id=_int(request.GET.get("exercise")),
        )
        chart = (
            aggregations.top_set_chart(
                request.user,
                exercise,
                context["range_key"],
                today,
            )
            if exercise is not None
            else _empty_chart()
        )
        context.update(
            {
                "exercise": exercise,
                "exercise_options": aggregations.weighted_exercises(request.user),
                "chart": chart,
                "has_chart": bool(chart["labels"]),
            }
        )
    elif tab == "prs":
        query = request.GET.get("q", "").strip()
        muscle_slug = request.GET.get("muscle", "").strip()
        context.update(
            {
                "query": query,
                "muscle_slug": muscle_slug,
                "table": aggregations.record_table(
                    request.user,
                    query=query,
                    muscle_slug=muscle_slug,
                ),
            }
        )
    else:
        metric = _metric(request.GET.get("metric", "sets"))
        exclude_tag = aggregations.tag_lookup(request.user, request.GET.get("exclude_tag"))
        context.update(
            {
                "metric": metric,
                "exclude_tag": exclude_tag,
                "chart": aggregations.weekly_volume(
                    request.user,
                    metric=metric,
                    tag_exclude=exclude_tag,
                    today=today,
                ),
            }
        )
        context["has_chart"] = bool(context["chart"]["series"])

    return render(request, "stats/index.html", context)


@require_GET
def api_top_set(request):
    """JSON top-set series for one exercise and range."""
    exercise = get_object_or_404(
        Exercise.objects.visible_to(request.user),
        pk=_int(request.GET.get("exercise")),
    )
    return JsonResponse(
        aggregations.top_set_chart(
            request.user,
            exercise,
            _range(request.GET.get("range", "3m")),
        )
    )


@require_GET
def api_volume(request):
    """JSON weekly volume by primary muscle group."""
    exclude_tag = aggregations.tag_lookup(request.user, request.GET.get("exclude_tag"))
    return JsonResponse(
        aggregations.weekly_volume(
            request.user,
            metric=_metric(request.GET.get("metric", "sets")),
            tag_exclude=exclude_tag,
        )
    )
