from datetime import date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from apps.exercises.models import Exercise
from apps.plans.models import ScheduledWorkout
from apps.workouts.models import Session
from apps.workouts.services import summary

from .factories import add_exercise, make_session

TODAY = date(2026, 11, 9)


def _scheduled(user, plan, plan_day, day, status=ScheduledWorkout.Status.COMPLETED):
    return ScheduledWorkout.objects.create(
        user=user,
        plan=plan,
        plan_day=plan_day,
        scheduled_date=day,
        status=status,
    )


def test_format_volume_groups_thousands_and_keeps_meaningful_decimals():
    assert summary.format_volume(Decimal("0")) == "0"
    assert summary.format_volume(Decimal("12000")) == "12,000"
    assert summary.format_volume(Decimal("1234.50")) == "1,234.5"


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_build_summary_reports_counts_volume_comparison_and_prs(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise
):
    prior_workout = _scheduled(user, active_plan, active_plan_day, date(2026, 11, 2))
    prior = make_session(
        user,
        day=date(2026, 11, 2),
        plan_day=active_plan_day,
        scheduled_workout=prior_workout,
    )
    add_exercise(
        prior,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 10},
            {"weight_lb": "100", "reps": 10},
            {"weight_lb": "100", "reps": 10},
        ],
    )

    workout = _scheduled(user, active_plan, active_plan_day, TODAY)
    session = make_session(
        user,
        day=TODAY,
        plan_day=active_plan_day,
        scheduled_workout=workout,
    )
    add_exercise(
        session,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 10, "difficulty": 6},
            {"weight_lb": "100", "reps": 12, "difficulty": 8},
            {"weight_lb": "110", "reps": 8, "difficulty": 10},
            {"status": "SKIPPED"},
            {"weight_lb": "90", "reps": 15, "difficulty": 4, "is_extra": True},
        ],
        target_sets=3,
        planned_sets=3,
        rep_min=8,
        rep_max=12,
    )

    result = summary.build_summary(session)

    assert result.duration_seconds == 50 * 60
    assert result.duration_label == "50:00"
    assert result.done_sets == 4
    assert result.planned_sets == 3
    assert result.extra_sets == 1
    assert result.skipped_sets == 1
    assert result.sets_label == "4 of 3 · +1 extra · 1 skipped"
    assert result.volume == Decimal("4430")
    assert result.volume_label == "4,430"
    assert result.comparison.direction == "up"
    assert result.comparison.delta_label == "+47.7%"
    assert result.comparison.prior_volume_label == "3,000"
    assert result.comparison.prior_date == date(2026, 11, 2)
    assert sorted(pr.kind for pr in result.prs) == ["heaviest", "reps"]
    assert result.avg_difficulty == 7.0
    assert [row.name for row in result.muscles] == ["Chest"]
    assert result.muscles[0].sets == 4
    assert result.increase_exercises == []
    assert result.adherence.completed == 2
    assert result.adherence.streak == 2


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_build_summary_groups_muscles_and_flags_ready_exercises(user, muscles, seeded_exercise):
    quads = Exercise.objects.create(
        user=None,
        name="Leg Extension",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    session = make_session(user, day=TODAY, kind=Session.Kind.UNSCHEDULED, title="Legs")
    add_exercise(
        session,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 12},
            {"weight_lb": "100", "reps": 12},
            {"weight_lb": "100", "reps": 12},
        ],
        order=0,
        target_sets=3,
        planned_sets=3,
        rep_max=12,
    )
    add_exercise(
        session,
        quads,
        [
            {"weight_lb": "120", "reps": 10},
            {"weight_lb": "120", "reps": 10},
            {"weight_lb": "120", "reps": 10},
            {"weight_lb": "120", "reps": 10},
            {"weight_lb": "120", "reps": 10},
        ],
        order=1,
        target_sets=5,
        planned_sets=5,
        rep_max=10,
    )

    result = summary.build_summary(session)

    assert [row.name for row in result.muscles] == ["Quads", "Chest"]
    assert [row.sets for row in result.muscles] == [5, 3]
    assert [row.share for row in result.muscles] == [62, 38]
    assert [row.bar_percent for row in result.muscles] == [100, 60]
    assert [exercise.exercise.name for exercise in result.increase_exercises] == [
        "Barbell Bench Press",
        "Leg Extension",
    ]


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_adherence_counts_resolved_statuses_and_streak(user, active_plan, active_plan_day):
    for day, status in (
        (date(2026, 11, 2), ScheduledWorkout.Status.MISSED),
        (date(2026, 11, 4), ScheduledWorkout.Status.MADE_UP),
        (date(2026, 11, 6), ScheduledWorkout.Status.COMPLETED),
        (TODAY, ScheduledWorkout.Status.COMPLETED),
        (date(2026, 11, 16), ScheduledWorkout.Status.PENDING),
    ):
        _scheduled(user, active_plan, active_plan_day, day, status=status)

    result = summary.adherence(active_plan, TODAY)

    assert result.completed == 2
    assert result.made_up == 1
    assert result.missed == 1
    assert result.streak == 3
    assert result.has_history is True


@pytest.mark.django_db
def test_adherence_is_none_without_a_plan_and_empty_before_history(user, plan):
    assert summary.adherence(None) is None

    result = summary.adherence(plan)

    assert result.completed == 0
    assert result.streak == 0
    assert result.has_history is False


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_unscheduled_comparison_uses_the_session_title(user, seeded_exercise):
    prior = make_session(
        user,
        day=date(2026, 11, 2),
        kind=Session.Kind.UNSCHEDULED,
        title="Extra push",
    )
    add_exercise(prior, seeded_exercise, [{"weight_lb": "100", "reps": 10}])
    session = make_session(
        user,
        day=TODAY,
        kind=Session.Kind.UNSCHEDULED,
        title="Extra push",
    )
    add_exercise(session, seeded_exercise, [{"weight_lb": "110", "reps": 10}])

    result = summary.build_summary(session)

    assert result.comparison.prior_date == date(2026, 11, 2)
    assert result.comparison.delta_label == "+10%"


@pytest.mark.django_db
def test_comparison_is_skipped_when_the_previous_session_has_no_volume(user, seeded_exercise):
    prior = make_session(
        user,
        day=date(2026, 11, 2),
        kind=Session.Kind.UNSCHEDULED,
        title="Extra push",
    )
    add_exercise(prior, seeded_exercise, [{"status": "SKIPPED"}])
    session = make_session(
        user,
        day=TODAY,
        kind=Session.Kind.UNSCHEDULED,
        title="Extra push",
    )
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 10}])

    result = summary.build_summary(session)

    assert result.comparison.prior_volume == Decimal("0")
    assert result.comparison.delta_percent is None
    assert result.comparison.direction == "flat"


@pytest.mark.django_db
def test_session_volume_counts_only_done_weight_reps_sets(user, muscles, seeded_exercise):
    bodyweight = Exercise.objects.create(
        user=None,
        name="Pull-up",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.BODYWEIGHT,
    )
    session = make_session(user, day=TODAY)
    add_exercise(
        session,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 10},
            {"weight_lb": "200", "reps": 10, "status": "SKIPPED"},
        ],
        order=0,
    )
    add_exercise(session, bodyweight, [{"weight_lb": "50", "reps": 10}], order=1)

    assert summary.session_volume(session) == Decimal("1000")


@pytest.mark.django_db
def test_retro_duration_uses_the_entered_duration(user, seeded_exercise):
    session = make_session(user, day=TODAY, duration_seconds=45 * 60)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 10}])

    result = summary.build_summary(session)

    assert result.duration_seconds == 45 * 60
    assert result.duration_label == "45:00"
