from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.exercises.models import Exercise
from apps.plans.models import Plan, PlanDay, PlanItem, ScheduledWorkout, Weekday


@pytest.mark.django_db
def test_plan_status_helpers(plan):
    assert plan.is_draft
    assert not plan.is_active
    assert not plan.is_archived

    plan.status = Plan.Status.ACTIVE
    assert plan.is_active
    assert not plan.is_draft

    plan.status = Plan.Status.ARCHIVED
    assert plan.is_archived


@pytest.mark.django_db
def test_plan_queryset_scopes_to_the_user(user, other_user, plan):
    other_plan = Plan.objects.create(
        user=other_user,
        name="Other block",
        start_date=date(2026, 11, 2),
    )

    assert list(Plan.objects.for_user(user)) == [plan]
    assert list(Plan.objects.for_user(other_user)) == [other_plan]
    assert list(Plan.objects.for_user(type("Anon", (), {"is_authenticated": False})())) == []


@pytest.mark.django_db
def test_one_active_plan_per_user_is_enforced(user, active_plan):
    with pytest.raises(IntegrityError):
        Plan.objects.create(
            user=user,
            name="Second active",
            start_date=date(2026, 11, 2),
            status=Plan.Status.ACTIVE,
        )


@pytest.mark.django_db
def test_plan_day_weekday_is_unique_per_plan(plan, plan_day):
    with pytest.raises(IntegrityError):
        PlanDay.objects.create(
            plan=plan,
            name="Another Monday",
            weekday=Weekday.MONDAY,
        )


@pytest.mark.django_db
def test_plan_day_short_label(plan_day):
    assert plan_day.weekday_short == "Mon"
    assert str(plan_day) == "Day A – Lower (Monday)"


@pytest.mark.django_db
def test_plan_item_weight_reps_summary(plan_item):
    assert plan_item.target_summary == "4 × 6–8"
    assert plan_item.rest_label == "120s"


@pytest.mark.django_db
def test_plan_item_single_rep_summary(plan_item):
    plan_item.rep_min = 8
    plan_item.rep_max = 8

    assert plan_item.target_summary == "4 × 8"


@pytest.mark.django_db
def test_plan_item_timed_summary(plan_day, seeded_exercise):
    seeded_exercise.tracking_type = Exercise.TrackingType.TIMED
    seeded_exercise.save()

    item = PlanItem.objects.create(
        plan_day=plan_day,
        exercise=seeded_exercise,
        target_sets=3,
        target_seconds=90,
    )

    assert item.target_summary == "3 × 1:30"


@pytest.mark.django_db
def test_plan_item_cardio_summary(plan_day, seeded_exercise):
    seeded_exercise.tracking_type = Exercise.TrackingType.CARDIO
    seeded_exercise.save()

    item = PlanItem.objects.create(
        plan_day=plan_day,
        exercise=seeded_exercise,
        target_sets=1,
        target_seconds=1800,
        target_distance_mi=Decimal("3.10"),
    )

    assert item.target_summary == "30:00 · 3.1 mi"


@pytest.mark.django_db
def test_plan_item_weight_distance_summary(plan_day, seeded_exercise):
    seeded_exercise.tracking_type = Exercise.TrackingType.WEIGHT_DISTANCE
    seeded_exercise.save()

    item = PlanItem.objects.create(
        plan_day=plan_day,
        exercise=seeded_exercise,
        target_sets=4,
        target_distance_mi=Decimal("0.50"),
    )

    assert item.target_summary == "4 × 0.5 mi"


@pytest.mark.django_db
def test_plan_item_falls_back_to_set_count(plan_item):
    plan_item.rep_min = None
    plan_item.rep_max = None

    assert plan_item.target_summary == "4 sets"


@pytest.mark.django_db
def test_scheduled_workout_string_and_scoping(user, other_user, plan, plan_day):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=plan,
        plan_day=plan_day,
        scheduled_date=date(2026, 11, 2),
    )
    other_workout = ScheduledWorkout.objects.create(
        user=other_user,
        plan=Plan.objects.create(
            user=other_user,
            name="Other",
            start_date=date(2026, 11, 2),
        ),
        plan_day=PlanDay.objects.create(
            plan=Plan.objects.get(user=other_user),
            name="Other day",
            weekday=Weekday.MONDAY,
        ),
        scheduled_date=date(2026, 11, 2),
    )

    assert str(workout) == f"{plan_day} on 2026-11-02"
    assert list(ScheduledWorkout.objects.for_user(user)) == [workout]
    assert list(ScheduledWorkout.objects.for_user(other_user)) == [other_workout]
