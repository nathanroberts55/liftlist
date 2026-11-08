"""Aggregations for the stats tabs and exercise detail charts (F-10).

Everything is computed from completed sessions on demand. The output of the
chart helpers is deliberately plain JSON-friendly data so the same dict can be
rendered with ``json_script`` and returned by ``/stats/api/...``.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.exercises.models import Exercise, MuscleGroup
from apps.workouts.models import Session, SessionExercise, SetLog
from apps.workouts.services import records
from apps.workouts.services.summary import (
    adherence,  # noqa: F401 - re-exported (TECH_SPEC §4.9)
    format_volume,
)

WEIGHT_TRACKING_TYPES = (
    Exercise.TrackingType.WEIGHT_REPS,
    Exercise.TrackingType.WEIGHT_DISTANCE,
)

RANGE_MONTHS = {"3m": 3, "6m": 6, "1y": 12}
RANGE_LABELS = (
    ("3m", "3M"),
    ("6m", "6M"),
    ("1y", "1Y"),
    ("all", "All"),
)
CHART_COLOR_COUNT = 8


# --- Shared helpers ---------------------------------------------------------


def _month_start(day: date, months_back: int) -> date:
    month = day.month - months_back
    year = day.year
    while month <= 0:
        month += 12
        year -= 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def range_start(range_key: str, today: date | None = None) -> date | None:
    """Translate a stats range key into an inclusive start date."""
    if range_key == "all":
        return None
    months = RANGE_MONTHS.get(range_key, RANGE_MONTHS["3m"])
    return _month_start(today or timezone.localdate(), months)


def _date_label(day: date) -> str:
    return f"{day:%b} {day.day}"


def _trim_decimal(value: Decimal | None) -> str:
    if value is None:
        return "—"
    text = format(value, "f")
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".") or "0"


def _muscle_colors() -> dict[int, int]:
    """Fixed color index per muscle group, following display order."""
    return {
        muscle.pk: index % CHART_COLOR_COUNT
        for index, muscle in enumerate(MuscleGroup.objects.order_by("display_order", "name"))
    }


def _completed_logs(user, *, since: date | None = None):
    queryset = SetLog.objects.filter(
        session_exercise__session__user=user,
        session_exercise__session__status=Session.Status.COMPLETED,
        status=SetLog.Status.DONE,
    ).select_related(
        "session_exercise__session",
        "session_exercise__exercise",
        "session_exercise__exercise__primary_muscle",
    )
    if since is not None:
        queryset = queryset.filter(session_exercise__session__performed_date__gte=since)
    return queryset


def _set_label(log: SetLog) -> str:
    """Compact label for a set in the chart tooltip."""
    weight = _trim_decimal(log.weight_lb)
    if log.reps is not None:
        return f"{weight} lb × {log.reps}"
    if log.distance_mi is not None:
        return f"{weight} lb × {_trim_decimal(log.distance_mi)} mi"
    return f"{weight} lb"


# --- Weight over time -------------------------------------------------------


def top_set_series(user, exercise, since: date | None = None) -> list[dict]:
    """One point per session date: the heaviest set and every set that day."""
    if exercise.tracking_type not in WEIGHT_TRACKING_TYPES:
        return []
    logs = list(
        _completed_logs(user, since=since)
        .filter(
            session_exercise__exercise=exercise,
            weight_lb__isnull=False,
        )
        .order_by(
            "session_exercise__session__performed_date",
            "session_exercise__session__completed_at",
            "session_exercise__session__pk",
            "set_number",
        )
    )
    if exercise.tracking_type == Exercise.TrackingType.WEIGHT_REPS:
        logs = [log for log in logs if (log.reps or 0) >= 1]

    grouped: dict[date, list[SetLog]] = {}
    for log in logs:
        grouped.setdefault(log.session_exercise.session.performed_date, []).append(log)

    points: list[dict] = []
    for day_logs in grouped.values():
        best = max(
            day_logs,
            key=lambda log: (log.weight_lb, log.reps or 0, log.set_number),
        )
        session = best.session_exercise.session
        points.append(
            {
                "date": session.performed_date.isoformat(),
                "label": _date_label(session.performed_date),
                "weight": float(best.weight_lb),
                "weight_label": _trim_decimal(best.weight_lb),
                "reps": best.reps,
                "session_id": session.pk,
                "sets": [
                    {
                        "label": _set_label(log),
                        "weight_label": _trim_decimal(log.weight_lb),
                        "reps": log.reps,
                    }
                    for log in day_logs
                ],
            }
        )
    points.sort(key=lambda point: point["date"])
    return points


def top_set_chart(user, exercise, range_key: str = "3m", today: date | None = None) -> dict:
    """Chart.js-ready top-set data plus the tooltip rows."""
    start = range_start(range_key, today)
    points = top_set_series(user, exercise, since=start)
    return {
        "labels": [point["label"] for point in points],
        "values": [point["weight"] for point in points],
        "tooltips": [" · ".join(row["label"] for row in point["sets"]) for point in points],
        "label": "Top set (lb)",
        "color_index": 0,
        "range": range_key,
        "exercise_id": exercise.pk,
    }


# --- Weekly volume ----------------------------------------------------------


def weekly_volume(
    user,
    weeks: int = 8,
    metric: str = "sets",
    *,
    tag_include=None,
    tag_exclude=None,
    today: date | None = None,
) -> dict:
    """Stacked weekly sets or tonnage, grouped by primary muscle group."""
    if metric not in ("sets", "tonnage"):
        metric = "sets"
    today = today or timezone.localdate()
    current_monday = today - timedelta(days=today.weekday())
    first_monday = current_monday - timedelta(weeks=weeks - 1)
    week_starts = [first_monday + timedelta(weeks=index) for index in range(weeks)]

    logs = _completed_logs(
        user,
        since=first_monday,
    ).filter(session_exercise__session__performed_date__lte=today)
    if tag_include is not None:
        logs = logs.filter(session_exercise__session__tags=tag_include)
    if tag_exclude is not None:
        logs = logs.exclude(session_exercise__session__tags=tag_exclude)

    colors = _muscle_colors()
    cells: dict[int, list[Decimal | int]] = {}
    muscles: dict[int, dict] = {}
    for log in logs:
        session_exercise = log.session_exercise
        performed_date = session_exercise.session.performed_date
        week_index = (performed_date - first_monday).days // 7
        if not 0 <= week_index < weeks:
            continue
        if metric == "sets":
            value: Decimal | int = 1
        else:
            if session_exercise.exercise.tracking_type != Exercise.TrackingType.WEIGHT_REPS:
                continue
            if log.weight_lb is None or log.reps is None:
                continue
            value = log.weight_lb * log.reps
        muscle = session_exercise.exercise.primary_muscle
        if muscle.pk not in cells:
            cells[muscle.pk] = [0] * weeks
            muscles[muscle.pk] = {
                "name": muscle.name,
                "slug": muscle.slug,
                "color_index": colors.get(muscle.pk, 0),
            }
        cells[muscle.pk][week_index] += value

    series = []
    for muscle_pk, values in cells.items():
        total = sum(values, Decimal("0") if metric == "tonnage" else 0)
        if not total:
            continue
        entry = muscles[muscle_pk]
        series.append(
            {
                **entry,
                "values": [float(value) if metric == "tonnage" else value for value in values],
                "total": float(total) if metric == "tonnage" else total,
                "total_label": (
                    format_volume(Decimal(str(total))) if metric == "tonnage" else str(total)
                ),
            }
        )
    series.sort(key=lambda entry: (-entry["total"], entry["name"]))

    return {
        "labels": [_date_label(day) for day in week_starts],
        "weeks": [day.isoformat() for day in week_starts],
        "series": series,
        "metric": metric,
        "unit": "lb" if metric == "tonnage" else "sets",
        "max": max((entry["total"] for entry in series), default=0),
    }


# --- Records and recent sessions -------------------------------------------


def record_table(user, *, query: str = "", muscle_slug: str = "") -> list[dict]:
    """Exercises with at least one weighted set, plus their current records."""
    exercises = Exercise.objects.visible_to(user).filter(
        tracking_type__in=WEIGHT_TRACKING_TYPES,
    )
    if query:
        exercises = exercises.filter(name__icontains=query)
    if muscle_slug:
        exercises = exercises.filter(primary_muscle__slug=muscle_slug)
    exercises = exercises.order_by("name")

    table = []
    for exercise in exercises:
        exercise_records = records.prs_for_exercise(user, exercise)
        if exercise_records.heaviest is None:
            continue
        table.append({"exercise": exercise, "records": exercise_records})
    return table


def recent_sessions(user, exercise, limit: int = 5) -> list[SessionExercise]:
    """The last completed SessionExercises for one exercise, newest first."""
    return list(
        SessionExercise.objects.filter(
            session__user=user,
            session__status=Session.Status.COMPLETED,
            exercise=exercise,
        )
        .select_related("session", "exercise")
        .prefetch_related("sets")
        .order_by("-session__performed_date", "-session__completed_at", "-pk")[:limit]
    )


def exercise_with_history(user, *, preferred_id=None) -> Exercise | None:
    """The requested exercise or the most recently trained weighted one."""
    options = weighted_exercises(user)
    if preferred_id is not None:
        preferred = options.filter(pk=preferred_id).first()
        if preferred is not None:
            return preferred
    latest = (
        SessionExercise.objects.filter(
            session__user=user,
            session__status=Session.Status.COMPLETED,
            exercise__tracking_type__in=WEIGHT_TRACKING_TYPES,
        )
        .select_related("exercise")
        .order_by("-session__performed_date", "-session__completed_at", "-pk")
        .first()
    )
    if latest is None:
        return None
    return options.filter(pk=latest.exercise_id).first()


def weighted_exercises(user):
    """Visible weighted exercises, for the progress tab's select."""
    return (
        Exercise.objects.visible_to(user)
        .filter(
            tracking_type__in=WEIGHT_TRACKING_TYPES,
            session_exercises__session__user=user,
            session_exercises__session__status=Session.Status.COMPLETED,
        )
        .distinct()
        .order_by("name")
    )


def tag_lookup(user, raw):
    """Resolve an optional tag id from a query string for a user."""
    from apps.workouts.models import Tag

    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return None
    return Tag.objects.filter(user=user, pk=pk).first()
