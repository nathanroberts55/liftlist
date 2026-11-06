"""Data for the Today screen (F-04)."""

from datetime import timedelta

from apps.workouts.models import Session
from apps.workouts.services import progression

from ..models import WEEKDAY_SHORT, Plan, ScheduledWorkout
from . import scheduling


def build_today(user, today) -> dict:
    """Return the active plan, today's workout, catch-up rows, and week strip."""
    scheduling.sync_statuses(user, today)
    in_progress_session = (
        Session.objects.filter(user=user, status=Session.Status.IN_PROGRESS)
        .select_related("scheduled_workout", "plan_day")
        .first()
    )
    plan = Plan.objects.active_for(user).first()
    if plan is None:
        return {
            "plan": None,
            "week_number": None,
            "total_weeks": None,
            "today_workout": None,
            "today_items": [],
            "catch_up": [],
            "week_days": [],
            "in_progress_session": in_progress_session,
        }

    scheduled = plan.scheduled_workouts.select_related("plan_day")
    today_workout = scheduled.filter(scheduled_date=today).first()
    today_items = []
    if today_workout is not None:
        today_items = list(
            today_workout.plan_day.items.select_related("exercise").order_by("order")
        )
        for item in today_items:
            item.increase = progression.flag_for_upcoming(
                user,
                item.exercise,
                today_workout.plan_day,
            )

    catch_up = list(
        scheduled.filter(
            status=ScheduledWorkout.Status.MISSED,
            scheduled_date__lt=today,
        ).order_by("-scheduled_date")[:4]
    )

    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    rows = {
        workout.scheduled_date: workout
        for workout in scheduled.filter(scheduled_date__gte=week_start, scheduled_date__lt=week_end)
    }
    week_days = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        workout = rows.get(day)
        week_days.append(
            {
                "date": day,
                "label": WEEKDAY_SHORT[offset],
                "letter": WEEKDAY_SHORT[offset][0],
                "is_today": day == today,
                "is_past": day < today,
                "workout": workout,
                "status": workout.status if workout else None,
            }
        )

    return {
        "plan": plan,
        "week_number": scheduling.week_number(plan, today),
        "total_weeks": plan.length_weeks,
        "today_workout": today_workout,
        "today_items": today_items,
        "catch_up": catch_up,
        "week_days": week_days,
        "in_progress_session": in_progress_session,
    }
