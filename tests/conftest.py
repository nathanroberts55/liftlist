import pytest
from django.contrib.auth import get_user_model

from apps.exercises.models import Exercise, MuscleGroup


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="lifter", password="correct-horse-battery")


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        username="other-lifter", password="correct-horse-battery"
    )


@pytest.fixture
def muscles(db):
    """The 12 muscle groups created by the exercises data migration."""
    return {muscle.name: muscle for muscle in MuscleGroup.objects.all()}


@pytest.fixture
def seeded_exercise(db, muscles):
    """A global exercise (``user = None``), as created by ``seed_exercises``."""
    return Exercise.objects.create(
        user=None,
        name="Barbell Bench Press",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )


@pytest.fixture
def custom_exercise(db, user, muscles):
    """A custom exercise owned by :func:`user`."""
    return Exercise.objects.create(
        user=user,
        name="Cable Fly",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )


@pytest.fixture
def plan(db, user):
    """A draft plan starting on Monday, Nov 2 2026."""
    from datetime import date

    from apps.plans.models import Plan

    return Plan.objects.create(
        user=user,
        name="Upper/Lower Block 3",
        split_type=Plan.SplitType.UPPER_LOWER,
        start_date=date(2026, 11, 2),
        length_weeks=4,
    )


@pytest.fixture
def active_plan(db, user):
    """An active plan. The caller generates its schedule when needed."""
    from datetime import date

    from apps.plans.models import Plan

    return Plan.objects.create(
        user=user,
        name="Active Block",
        split_type=Plan.SplitType.UPPER_LOWER,
        start_date=date(2026, 11, 2),
        length_weeks=4,
        status=Plan.Status.ACTIVE,
    )


@pytest.fixture
def active_plan_day(db, active_plan):
    """A Monday Plan Day belonging to :func:`active_plan`."""
    from apps.plans.models import PlanDay, Weekday

    return PlanDay.objects.create(
        plan=active_plan,
        name="Day A – Lower",
        weekday=Weekday.MONDAY,
        order=0,
    )


@pytest.fixture
def plan_day(db, plan):
    """A Monday Plan Day belonging to :func:`plan`."""
    from apps.plans.models import PlanDay, Weekday

    return PlanDay.objects.create(
        plan=plan,
        name="Day A – Lower",
        weekday=Weekday.MONDAY,
        order=0,
    )


@pytest.fixture
def plan_item(db, plan_day, seeded_exercise):
    """A ``WEIGHT_REPS`` item in :func:`plan_day`."""
    from apps.plans.models import PlanItem

    return PlanItem.objects.create(
        plan_day=plan_day,
        exercise=seeded_exercise,
        order=0,
        target_sets=4,
        rep_min=6,
        rep_max=8,
        rest_seconds=120,
    )


@pytest.fixture
def active_plan_item(db, active_plan_day, seeded_exercise):
    """A ``WEIGHT_REPS`` item in :func:`active_plan_day`."""
    from apps.plans.models import PlanItem

    return PlanItem.objects.create(
        plan_day=active_plan_day,
        exercise=seeded_exercise,
        order=0,
        target_sets=4,
        rep_min=6,
        rep_max=8,
        rest_seconds=120,
    )
