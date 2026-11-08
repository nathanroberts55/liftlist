"""Model factories shared by the M5 summary and stats tests."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.workouts.models import Session, SessionExercise, SetLog


def make_session(
    user,
    *,
    day,
    title="Day A – Lower",
    plan_day=None,
    scheduled_workout=None,
    kind=Session.Kind.SCHEDULED,
    status=Session.Status.COMPLETED,
    duration_seconds=None,
    started_at=None,
    completed_at=None,
):
    """Create a Session, defaulting to a completed 50-minute workout."""
    if started_at is None:
        started_at = timezone.make_aware(datetime.combine(day, time(12, 0)))
    if completed_at is None and status == Session.Status.COMPLETED:
        completed_at = started_at + timedelta(minutes=50)
    return Session.objects.create(
        user=user,
        kind=kind,
        scheduled_workout=scheduled_workout,
        plan_day=plan_day,
        title=title,
        performed_date=day,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration_seconds,
    )


def add_exercise(
    session,
    exercise,
    sets,
    *,
    order=0,
    target_sets=None,
    planned_sets=None,
    rep_min=None,
    rep_max=None,
    rest_seconds=90,
):
    """Attach a SessionExercise plus its sets.

    Each entry in ``sets`` may set ``weight_lb``, ``reps``, ``difficulty``,
    ``status``, and ``is_extra``; DONE is the default.
    """
    target_sets = target_sets if target_sets is not None else len(sets)
    planned_sets = planned_sets if planned_sets is not None else target_sets
    session_exercise = SessionExercise.objects.create(
        session=session,
        exercise=exercise,
        order=order,
        target_sets=target_sets,
        planned_sets=planned_sets,
        rep_min=rep_min,
        rep_max=rep_max,
        rest_seconds=rest_seconds,
    )
    for index, values in enumerate(sets, start=1):
        SetLog.objects.create(
            session_exercise=session_exercise,
            set_number=index,
            status=values.get("status", SetLog.Status.DONE),
            weight_lb=_decimal(values.get("weight_lb")),
            reps=values.get("reps"),
            duration_seconds=values.get("duration_seconds"),
            distance_mi=_decimal(values.get("distance_mi")),
            difficulty=values.get("difficulty"),
            is_extra=values.get("is_extra", False),
        )
    return session_exercise


def _decimal(value):
    if value is None:
        return None
    return Decimal(str(value))
