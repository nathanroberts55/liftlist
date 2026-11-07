"""History calendar, list, and day detail services (F-09)."""

import calendar
from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.plans.models import Plan, ScheduledWorkout
from apps.plans.services import scheduling

from ..models import Session
from . import tags as tag_services

STATUS_ORDER = ("COMPLETED", "MISSED", "MADE_UP", "UNSCHEDULED", "PENDING")
STATUS_LABELS = {
    "COMPLETED": "Completed",
    "MISSED": "Missed",
    "MADE_UP": "Made up",
    "UNSCHEDULED": "Unscheduled session",
    "PENDING": "Pending",
}


def _session_queryset(user):
    return (
        Session.objects.filter(user=user, status=Session.Status.COMPLETED)
        .select_related(
            "plan_day",
            "scheduled_workout",
            "scheduled_workout__plan",
            "scheduled_workout__plan_day",
        )
        .prefetch_related("tags")
    )


def filter_sessions(queryset, *, tag=None, exclude_tag=None, plan=None):
    if tag is not None:
        queryset = queryset.filter(tags=tag)
    if exclude_tag is not None:
        queryset = queryset.exclude(tags=exclude_tag)
    if plan is not None:
        queryset = queryset.filter(Q(scheduled_workout__plan=plan) | Q(plan_day__plan=plan))
    return queryset


def list_sessions(user, *, tag=None, exclude_tag=None, plan=None):
    """Completed sessions, newest first, with optional tag and plan filters."""
    return filter_sessions(
        _session_queryset(user),
        tag=tag,
        exclude_tag=exclude_tag,
        plan=plan,
    ).order_by("-performed_date", "-started_at", "-pk")


def _session_dot(session: Session) -> str:
    """Dots describe what happened on the day the session was performed.

    A make-up workout's original date carries the made-up ring from its
    Scheduled Workout; the performed date is simply a completed session.
    """
    if session.kind == Session.Kind.UNSCHEDULED:
        return "UNSCHEDULED"
    return "COMPLETED"


def _dot(status: str) -> dict:
    return {"status": status, "label": STATUS_LABELS[status]}


def _order_dots(dots) -> list[dict]:
    seen = set()
    ordered = []
    for status in STATUS_ORDER:
        if status in dots and status not in seen:
            ordered.append(_dot(status))
            seen.add(status)
    return ordered


def calendar_month(
    user,
    year,
    month,
    *,
    tag=None,
    exclude_tag=None,
    plan=None,
    today=None,
):
    """Return a Monday-first month grid and the entries for each visible day."""
    today = today or timezone.localdate()
    weeks_dates = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    start_date = weeks_dates[0][0]
    end_date = weeks_dates[-1][-1]

    sessions = filter_sessions(
        _session_queryset(user).filter(performed_date__range=(start_date, end_date)),
        tag=tag,
        exclude_tag=exclude_tag,
        plan=plan,
    )
    workouts = (
        ScheduledWorkout.objects.for_user(user)
        .filter(scheduled_date__range=(start_date, end_date))
        .select_related("plan", "plan_day", "session")
        .order_by("scheduled_date", "plan_day__order")
    )
    if plan is not None:
        workouts = workouts.filter(plan=plan)
    if tag is not None or exclude_tag is not None:
        workouts = workouts.filter(
            pk__in=sessions.exclude(scheduled_workout__isnull=True).values("scheduled_workout_id")
        )

    sessions_by_date: dict[date, list[Session]] = {}
    for session in sessions:
        sessions_by_date.setdefault(session.performed_date, []).append(session)
    workouts_by_date: dict[date, list[ScheduledWorkout]] = {}
    for workout in workouts:
        workouts_by_date.setdefault(workout.scheduled_date, []).append(workout)

    day_entries: dict[date, list[dict]] = {}
    dot_statuses: dict[date, set[str]] = {}
    for day in (
        start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)
    ):
        entries: list[dict] = []
        statuses: set[str] = set()
        represented_sessions: set[int] = set()
        for workout in workouts_by_date.get(day, []):
            linked_session = getattr(workout, "session", None)
            if linked_session is not None and linked_session.performed_date == day:
                represented_sessions.add(linked_session.pk)
            entries.append(
                {
                    "type": "scheduled",
                    "workout": workout,
                    "session": (
                        linked_session
                        if linked_session is not None and linked_session.performed_date == day
                        else None
                    ),
                    "status": workout.status,
                    "status_label": workout.get_status_display(),
                }
            )
            statuses.add(workout.status)
        for session in sessions_by_date.get(day, []):
            status = _session_dot(session)
            statuses.add(status)
            if session.pk in represented_sessions:
                continue
            entries.append(
                {
                    "type": "session",
                    "workout": None,
                    "session": session,
                    "status": status,
                    "status_label": STATUS_LABELS[status],
                }
            )
        if entries:
            day_entries[day] = entries
        if statuses:
            dot_statuses[day] = statuses

    weeks = []
    for week in weeks_dates:
        row = []
        for day in week:
            row.append(
                {
                    "date": day,
                    "day": day.day,
                    "in_month": day.month == month,
                    "is_today": day == today,
                    "dots": _order_dots(dot_statuses.get(day, set())),
                    "has_entries": bool(day_entries.get(day)),
                }
            )
        weeks.append(row)

    return {
        "weeks": weeks,
        "day_entries": day_entries,
        "start_date": start_date,
        "end_date": end_date,
    }


def _default_selected_day(year, month, weeks, day_entries, today):
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    if first <= today <= last:
        return today
    for week in weeks:
        for day in week:
            if day["in_month"] and day_entries.get(day["date"]):
                return day["date"]
    return first


def _parse_day(raw, year, month):
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.year != year or parsed.month != month:
        return None
    return parsed


def build_history(
    user,
    *,
    view="calendar",
    year=None,
    month=None,
    tag=None,
    exclude_tag=None,
    plan=None,
    selected_day=None,
    today=None,
):
    """Build the context shared by the calendar and list views."""
    today = today or timezone.localdate()
    scheduling.sync_statuses(user, today)
    year = year or today.year
    month = month or today.month
    tags = list(tag_services.list_tags(user))
    plans = list(Plan.objects.for_user(user).order_by("-updated_at", "name"))
    filters = {
        "tag": tag,
        "exclude_tag": exclude_tag,
        "plan": plan,
    }

    if view == "list":
        sessions = list_sessions(user, tag=tag, exclude_tag=exclude_tag, plan=plan)
        return {
            "view": "list",
            "tags": tags,
            "plans": plans,
            "filters": filters,
            "sessions": sessions,
            "session_count": len(sessions),
            "month": f"{year:04d}-{month:02d}",
        }

    calendar_data = calendar_month(
        user,
        year,
        month,
        tag=tag,
        exclude_tag=exclude_tag,
        plan=plan,
        today=today,
    )
    selected = _parse_day(selected_day, year, month)
    if selected is None:
        selected = _default_selected_day(
            year,
            month,
            calendar_data["weeks"],
            calendar_data["day_entries"],
            today,
        )
    previous = date(year, month, 1) - timedelta(days=1)
    following = date(year, month, calendar.monthrange(year, month)[1]) + timedelta(days=1)
    return {
        "view": "calendar",
        "tags": tags,
        "plans": plans,
        "filters": filters,
        "weeks": calendar_data["weeks"],
        "selected_day": selected,
        "selected_entries": calendar_data["day_entries"].get(selected, []),
        "month": f"{year:04d}-{month:02d}",
        "month_label": date(year, month, 1).strftime("%B %Y"),
        "prev_month": f"{previous.year:04d}-{previous.month:02d}",
        "next_month": f"{following.year:04d}-{following.month:02d}",
        "weekday_letters": ("M", "T", "W", "T", "F", "S", "S"),
    }
