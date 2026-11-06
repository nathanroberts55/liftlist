from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.plans.models import Plan, PlanDay, ScheduledWorkout, Weekday
from apps.plans.services.scheduling import (
    activate_plan,
    archive_plan,
    generate_schedule,
    mark_missed,
    monday_of,
    recompute_status_after_session_change,
    regenerate_future,
    resolve_status_on_complete,
    sync_statuses,
    week_number,
)

TODAY = date(2026, 11, 9)


def _dates(plan):
    return list(
        plan.scheduled_workouts.order_by("scheduled_date").values_list("scheduled_date", flat=True)
    )


def test_monday_of_returns_the_week_start():
    assert monday_of(date(2026, 11, 12)) == date(2026, 11, 9)
    assert monday_of(date(2026, 11, 9)) == date(2026, 11, 9)
    assert monday_of(date(2026, 11, 15)) == date(2026, 11, 9)


@pytest.mark.django_db
def test_week_number_is_one_based(active_plan, active_plan_day):
    assert week_number(active_plan, date(2026, 11, 2)) == 1
    assert week_number(active_plan, date(2026, 11, 9)) == 2
    assert week_number(active_plan, date(2026, 11, 16)) == 3


@pytest.mark.django_db
def test_week_number_clamps_before_the_start(active_plan, active_plan_day):
    assert week_number(active_plan, date(2026, 10, 26)) == 1


@pytest.mark.django_db
def test_generate_schedule_creates_fixed_length_occurrences(active_plan, active_plan_day):
    created = generate_schedule(active_plan, TODAY)

    assert created == 4
    assert _dates(active_plan) == [
        date(2026, 11, 2),
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
    ]


@pytest.mark.django_db
def test_generate_schedule_is_idempotent(active_plan, active_plan_day):
    generate_schedule(active_plan, TODAY)
    created = generate_schedule(active_plan, TODAY)

    assert created == 0
    assert active_plan.scheduled_workouts.count() == 4


@pytest.mark.django_db
def test_generate_schedule_skips_dates_before_the_start(active_plan):
    PlanDay.objects.create(
        plan=active_plan,
        name="Day B",
        weekday=Weekday.THURSDAY,
        order=Weekday.THURSDAY,
    )
    active_plan.start_date = date(2026, 11, 5)  # Thursday
    active_plan.save(update_fields=["start_date"])

    generate_schedule(active_plan, TODAY)

    assert _dates(active_plan) == [
        date(2026, 11, 5),
        date(2026, 11, 12),
        date(2026, 11, 19),
        date(2026, 11, 26),
    ]


@pytest.mark.django_db
def test_generate_schedule_for_an_open_ended_plan_uses_the_horizon(active_plan, active_plan_day):
    active_plan.length_weeks = None
    active_plan.save(update_fields=["length_weeks"])

    generate_schedule(active_plan, TODAY, horizon_days=14)

    assert _dates(active_plan) == [
        date(2026, 11, 2),
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
    ]


@pytest.mark.django_db
def test_generate_schedule_without_days_does_nothing(active_plan):
    assert generate_schedule(active_plan, TODAY) == 0


@pytest.mark.django_db
def test_activate_plan_archives_the_current_plan_and_schedules_the_new(
    user, active_plan, active_plan_day, plan
):
    generate_schedule(active_plan, TODAY)
    assert active_plan.scheduled_workouts.count() == 4
    new_day = PlanDay.objects.create(
        plan=plan,
        name="Day B",
        weekday=Weekday.THURSDAY,
        order=Weekday.THURSDAY,
    )

    activate_plan(plan, TODAY)

    active_plan.refresh_from_db()
    plan.refresh_from_db()
    assert active_plan.status == Plan.Status.ARCHIVED
    assert active_plan.archived_at is not None
    assert plan.status == Plan.Status.ACTIVE
    assert plan.activated_at is not None
    assert set(_dates(plan)) == {
        date(2026, 11, 5),
        date(2026, 11, 12),
        date(2026, 11, 19),
        date(2026, 11, 26),
    }
    assert new_day.scheduled_workouts.count() == 4
    # Archiving the old plan removes its future pending rows but keeps the past.
    assert _dates(active_plan) == [date(2026, 11, 2)]


@pytest.mark.django_db
def test_activate_plan_is_a_no_op_for_an_already_active_plan(active_plan, active_plan_day):
    generate_schedule(active_plan, TODAY)

    activate_plan(active_plan, TODAY)

    active_plan.refresh_from_db()
    assert active_plan.status == Plan.Status.ACTIVE
    assert active_plan.scheduled_workouts.count() == 4


@pytest.mark.django_db
def test_regenerate_future_keeps_past_rows(active_plan, active_plan_day):
    generate_schedule(active_plan, TODAY)
    weekday_plan_day = PlanDay.objects.create(
        plan=active_plan,
        name="Day B",
        weekday=Weekday.WEDNESDAY,
        order=Weekday.WEDNESDAY,
    )

    regenerate_future(active_plan, TODAY)

    assert list(
        active_plan.scheduled_workouts.filter(plan_day=active_plan_day)
        .order_by("scheduled_date")
        .values_list("scheduled_date", flat=True)
    ) == [
        date(2026, 11, 2),
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
    ]
    assert list(
        weekday_plan_day.scheduled_workouts.order_by("scheduled_date").values_list(
            "scheduled_date", flat=True
        )
    ) == [
        date(2026, 11, 11),
        date(2026, 11, 18),
        date(2026, 11, 25),
    ]


@pytest.mark.django_db
def test_regenerate_future_ignores_a_non_active_plan(plan, plan_day):
    assert regenerate_future(plan, TODAY) == 0
    assert plan.scheduled_workouts.count() == 0


@pytest.mark.django_db
def test_archive_plan_removes_future_pending_but_keeps_past(active_plan, active_plan_day):
    ScheduledWorkout.objects.create(
        user=active_plan.user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=date(2026, 11, 2),
        status=ScheduledWorkout.Status.COMPLETED,
    )
    ScheduledWorkout.objects.create(
        user=active_plan.user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    ScheduledWorkout.objects.create(
        user=active_plan.user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=date(2026, 11, 16),
    )

    archive_plan(active_plan, TODAY)

    active_plan.refresh_from_db()
    assert active_plan.status == Plan.Status.ARCHIVED
    assert active_plan.archived_at is not None
    assert _dates(active_plan) == [date(2026, 11, 2)]


@pytest.mark.django_db
def test_sync_statuses_marks_overdue_pending_workouts_missed(active_plan, active_plan_day):
    for day in (date(2026, 11, 2), TODAY, date(2026, 11, 16)):
        ScheduledWorkout.objects.create(
            user=active_plan.user,
            plan=active_plan,
            plan_day=active_plan_day,
            scheduled_date=day,
        )

    updated = sync_statuses(active_plan.user, TODAY)

    assert updated == 1
    statuses = dict(active_plan.scheduled_workouts.values_list("scheduled_date", "status"))
    assert statuses[date(2026, 11, 2)] == ScheduledWorkout.Status.MISSED
    assert statuses[TODAY] == ScheduledWorkout.Status.PENDING
    assert statuses[date(2026, 11, 16)] == ScheduledWorkout.Status.PENDING


@pytest.mark.django_db
def test_sync_statuses_extends_an_open_ended_active_plan(active_plan, active_plan_day):
    active_plan.length_weeks = None
    active_plan.save(update_fields=["length_weeks"])
    generate_schedule(active_plan, TODAY, horizon_days=0)
    assert active_plan.scheduled_workouts.count() == 2

    sync_statuses(active_plan.user, TODAY)

    assert _dates(active_plan) == [
        date(2026, 11, 2),
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
    ]


@pytest.mark.django_db
def test_sync_statuses_does_not_extend_a_fixed_plan(active_plan, active_plan_day):
    generate_schedule(active_plan, TODAY)
    before = active_plan.scheduled_workouts.count()

    sync_statuses(active_plan.user, TODAY)

    assert active_plan.scheduled_workouts.count() == before


@pytest.mark.django_db
def test_mark_missed_only_works_for_today(active_plan, active_plan_day):
    yesterday = ScheduledWorkout.objects.create(
        user=active_plan.user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=date(2026, 11, 8),
    )

    with pytest.raises(ValidationError):
        mark_missed(yesterday, TODAY)


@pytest.mark.django_db
def test_mark_missed_sets_the_manual_flag(active_plan, active_plan_day):
    workout = ScheduledWorkout.objects.create(
        user=active_plan.user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )

    mark_missed(workout, TODAY)

    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MISSED
    assert workout.marked_missed_manually is True


@pytest.mark.django_db
def test_mark_missed_rejects_completed_workouts(active_plan, active_plan_day):
    workout = ScheduledWorkout.objects.create(
        user=active_plan.user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
        status=ScheduledWorkout.Status.COMPLETED,
    )

    with pytest.raises(ValidationError):
        mark_missed(workout, TODAY)


@pytest.mark.django_db
def test_resolve_status_on_complete(active_plan, active_plan_day):
    workout = ScheduledWorkout.objects.create(
        user=active_plan.user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )

    resolve_status_on_complete(workout, TODAY)
    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.COMPLETED

    resolve_status_on_complete(workout, date(2026, 11, 10))
    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MADE_UP


@pytest.mark.django_db
def test_recompute_status_after_session_change(active_plan, active_plan_day):
    workout = ScheduledWorkout.objects.create(
        user=active_plan.user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=date(2026, 11, 2),
        status=ScheduledWorkout.Status.COMPLETED,
    )

    recompute_status_after_session_change(workout, TODAY, has_completed_session=False)

    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MISSED
    assert workout.marked_missed_manually is False
