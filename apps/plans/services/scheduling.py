"""Scheduling services for plans and their workouts (F-04).

Dates are local dates. ``today`` is injected so services stay deterministic in
tests, while views pass ``timezone.localdate()``.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from ..models import Plan, ScheduledWorkout


def monday_of(day):
    """Return the Monday of the ISO week containing ``day``."""
    return day - timedelta(days=day.weekday())


def week_number(plan, today) -> int:
    """Weeks since the plan start + 1. Clamped to 1 before the start date."""
    weeks = ((monday_of(today) - monday_of(plan.start_date)).days // 7) + 1
    return max(1, weeks)


def _schedule_bounds(plan, today, horizon_days):
    """Return ``(week_count, last_date)`` for one generation pass."""
    if plan.length_weeks is None:
        last_date = today + timedelta(days=horizon_days)
        week_count = ((monday_of(last_date) - monday_of(plan.start_date)).days // 7) + 1
    else:
        last_date = None
        week_count = plan.length_weeks
    return max(week_count, 0), last_date


def generate_schedule(plan, today, horizon_days: int = 14, start_from=None) -> int:
    """Create missing Scheduled Workouts for a plan. Idempotent.

    ``start_from`` limits generation to dates on or after it. Activation uses the
    plan's own start date; plan edits and open-ended extensions only add today
    and later so they never backfill the past.
    """
    week_count, last_date = _schedule_bounds(plan, today, horizon_days)
    if week_count <= 0:
        return 0

    earliest = start_from if start_from is not None else plan.start_date
    days = list(plan.days.all())
    if not days:
        return 0

    existing = set(
        ScheduledWorkout.objects.filter(plan=plan).values_list("plan_day_id", "scheduled_date")
    )
    first_monday = monday_of(plan.start_date)
    created = 0
    for week_index in range(week_count):
        week_start = first_monday + timedelta(weeks=week_index)
        for day in days:
            scheduled_date = week_start + timedelta(days=day.weekday)
            if scheduled_date < plan.start_date or scheduled_date < earliest:
                continue
            if last_date is not None and scheduled_date > last_date:
                continue
            if (day.id, scheduled_date) in existing:
                continue
            ScheduledWorkout.objects.create(
                user=plan.user,
                plan=plan,
                plan_day=day,
                scheduled_date=scheduled_date,
            )
            existing.add((day.id, scheduled_date))
            created += 1
    return created


def _delete_future_pending(plan, today) -> None:
    """Remove future pending rows. Linked sessions must be handled in M3."""
    plan.scheduled_workouts.filter(
        status=ScheduledWorkout.Status.PENDING,
        scheduled_date__gte=today,
    ).delete()


def _archive_without_saving(plan, today) -> None:
    _delete_future_pending(plan, today)
    plan.status = Plan.Status.ARCHIVED
    plan.archived_at = timezone.now()


@transaction.atomic
def activate_plan(plan, today) -> None:
    """Make ``plan`` the single active plan and generate its schedule."""
    current = (
        Plan.objects.select_for_update()
        .filter(user=plan.user, status=Plan.Status.ACTIVE)
        .exclude(pk=plan.pk)
        .first()
    )
    if current is not None:
        _archive_without_saving(current, today)
        current.save(update_fields=["status", "archived_at", "updated_at"])

    if plan.status != Plan.Status.ACTIVE:
        plan.status = Plan.Status.ACTIVE
        plan.activated_at = timezone.now()
        plan.archived_at = None
        plan.save(update_fields=["status", "activated_at", "archived_at", "updated_at"])

    generate_schedule(plan, today)


@transaction.atomic
def regenerate_future(plan, today) -> int:
    """Rebuild today-and-later pending rows after a plan edit."""
    if plan.status != Plan.Status.ACTIVE:
        return 0
    _delete_future_pending(plan, today)
    return generate_schedule(plan, today, start_from=today)


@transaction.atomic
def archive_plan(plan, today) -> None:
    """End a plan without touching past or completed workouts."""
    _delete_future_pending(plan, today)
    plan.status = Plan.Status.ARCHIVED
    plan.archived_at = timezone.now()
    plan.save(update_fields=["status", "archived_at", "updated_at"])


def sync_statuses(user, today) -> int:
    """Mark overdue pending workouts missed and extend an open-ended plan."""
    updated = (
        ScheduledWorkout.objects.for_user(user)
        .filter(status=ScheduledWorkout.Status.PENDING, scheduled_date__lt=today)
        .update(status=ScheduledWorkout.Status.MISSED, updated_at=timezone.now())
    )

    active = Plan.objects.active_for(user).first()
    if active is not None and active.length_weeks is None:
        horizon_end = today + timedelta(days=14)
        latest = active.scheduled_workouts.aggregate(latest=Max("scheduled_date"))["latest"]
        if latest is None or latest < horizon_end:
            generate_schedule(active, today, start_from=today)
    return updated


def mark_missed(scheduled_workout, today) -> None:
    """Manually mark today's scheduled workout as missed."""
    if scheduled_workout.scheduled_date != today:
        raise ValidationError("You can only mark today's workout as missed.")
    if scheduled_workout.status in (
        ScheduledWorkout.Status.COMPLETED,
        ScheduledWorkout.Status.MADE_UP,
    ):
        raise ValidationError("That workout is already complete.")
    if scheduled_workout.status == ScheduledWorkout.Status.MISSED:
        return
    scheduled_workout.status = ScheduledWorkout.Status.MISSED
    scheduled_workout.marked_missed_manually = True
    scheduled_workout.save(update_fields=["status", "marked_missed_manually", "updated_at"])


def resolve_status_on_complete(scheduled_workout, performed_date) -> None:
    """Set COMPLETED or MADE_UP when a session is finished (used in M3)."""
    if performed_date == scheduled_workout.scheduled_date:
        status = ScheduledWorkout.Status.COMPLETED
    else:
        status = ScheduledWorkout.Status.MADE_UP
    if scheduled_workout.status != status:
        scheduled_workout.status = status
        scheduled_workout.save(update_fields=["status", "updated_at"])


def recompute_status_after_session_change(
    scheduled_workout, today, *, has_completed_session: bool, performed_date=None
) -> None:
    """Recompute a workout status after a session is deleted or re-dated (M3)."""
    if has_completed_session and performed_date is not None:
        resolve_status_on_complete(scheduled_workout, performed_date)
        return
    status = (
        ScheduledWorkout.Status.PENDING
        if scheduled_workout.scheduled_date >= today
        else ScheduledWorkout.Status.MISSED
    )
    if scheduled_workout.status != status:
        scheduled_workout.status = status
        scheduled_workout.marked_missed_manually = False
        scheduled_workout.save(update_fields=["status", "marked_missed_manually", "updated_at"])
