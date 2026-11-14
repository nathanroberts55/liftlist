from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.plans.models import PlanDay, Weekday
from apps.workouts.models import Session, SessionExercise, SetLog
from apps.workouts.services import progression

TODAY = date(2026, 11, 9)


def _past(
    user,
    exercise,
    day,
    sets,
    *,
    plan_day=None,
    rep_min=6,
    rep_max=8,
    planned_sets=None,
    extra_sets=(),
):
    session = Session.objects.create(
        user=user,
        kind=Session.Kind.SCHEDULED,
        plan_day=plan_day,
        title="Past workout",
        performed_date=day,
        status=Session.Status.COMPLETED,
        started_at=timezone.now(),
        completed_at=timezone.now(),
    )
    session_exercise = SessionExercise.objects.create(
        session=session,
        exercise=exercise,
        order=0,
        target_sets=len(sets),
        planned_sets=planned_sets if planned_sets is not None else len(sets),
        rep_min=rep_min,
        rep_max=rep_max,
    )
    for number, (weight, reps) in enumerate(sets, start=1):
        SetLog.objects.create(
            session_exercise=session_exercise,
            set_number=number,
            status=SetLog.Status.DONE,
            weight_lb=weight,
            reps=reps,
        )
    for offset, (weight, reps) in enumerate(extra_sets, start=len(sets) + 1):
        SetLog.objects.create(
            session_exercise=session_exercise,
            set_number=offset,
            status=SetLog.Status.DONE,
            is_extra=True,
            weight_lb=weight,
            reps=reps,
        )
    return session_exercise


def _current(user, exercise, **kwargs):
    session = Session.objects.create(
        user=user,
        kind=Session.Kind.SCHEDULED,
        title="Current workout",
        performed_date=TODAY,
        status=Session.Status.IN_PROGRESS,
    )
    defaults = {
        "session": session,
        "exercise": exercise,
        "order": 0,
        "target_sets": 3,
        "planned_sets": 3,
        "rep_min": 6,
        "rep_max": 8,
    }
    defaults.update(kwargs)
    return SessionExercise.objects.create(**defaults)


@pytest.mark.django_db
def test_last_time_uses_the_most_recent_completed_session(user, seeded_exercise):
    older = _past(user, seeded_exercise, date(2026, 11, 2), [(185, 8)])
    newer = _past(user, seeded_exercise, date(2026, 11, 5), [(225, 8)])

    assert progression.last_time(user, seeded_exercise).pk == newer.pk
    assert progression.last_time(user, seeded_exercise).pk != older.pk


@pytest.mark.django_db
def test_last_time_prefers_the_same_plan_day(user, seeded_exercise, active_plan):
    other_day = PlanDay.objects.create(
        plan=active_plan,
        name="Day B",
        weekday=Weekday.TUESDAY,
        order=1,
    )
    matching_day = PlanDay.objects.create(
        plan=active_plan,
        name="Day C",
        weekday=Weekday.WEDNESDAY,
        order=2,
    )
    newer_other_day = _past(
        user,
        seeded_exercise,
        date(2026, 11, 5),
        [(185, 8)],
        plan_day=other_day,
    )
    older_same_day = _past(
        user,
        seeded_exercise,
        date(2026, 11, 1),
        [(225, 8)],
        plan_day=matching_day,
    )

    assert progression.last_time(user, seeded_exercise, matching_day).pk == older_same_day.pk
    assert progression.last_time(user, seeded_exercise).pk == newer_other_day.pk


@pytest.mark.django_db
def test_last_time_ignores_an_in_progress_session(user, seeded_exercise):
    _past(user, seeded_exercise, date(2026, 11, 2), [(185, 8)])
    _current(user, seeded_exercise)

    last = progression.last_time(user, seeded_exercise)

    assert last.session.status == Session.Status.COMPLETED


@pytest.mark.django_db
def test_last_time_can_exclude_the_current_session(user, seeded_exercise):
    current = _past(user, seeded_exercise, date(2026, 11, 5), [(225, 8)])
    older = _past(user, seeded_exercise, date(2026, 11, 2), [(185, 8)])

    last = progression.last_time(user, seeded_exercise, exclude_session=current.session)

    assert last.pk == older.pk


@pytest.mark.django_db
def test_prefill_matches_the_set_number_then_falls_back_to_the_last_set(user, seeded_exercise):
    _past(
        user,
        seeded_exercise,
        date(2026, 11, 5),
        [(225, 8), (215, 8), (205, 7)],
    )
    current = _current(user, seeded_exercise)

    assert progression.prefill(user, current, 1)["weight_lb"] == 225
    assert progression.prefill(user, current, 1)["reps"] == 8
    assert progression.prefill(user, current, 2)["weight_lb"] == 215
    assert progression.prefill(user, current, 3)["weight_lb"] == 205
    assert progression.prefill(user, current, 3)["reps"] == 7
    assert progression.prefill(user, current, 4)["weight_lb"] == 205
    assert progression.prefill(user, current, 4)["reps"] == 8


@pytest.mark.django_db
def test_prefill_without_history_uses_session_targets(user, seeded_exercise):
    current = _current(user, seeded_exercise, rep_max=10)

    values = progression.prefill(user, current, 1)

    assert values == {
        "weight_lb": None,
        "reps": 10,
        "duration_seconds": None,
        "distance_m": None,
    }


@pytest.mark.django_db
def test_prefill_uses_the_exercise_targets_for_timed_sets(user, muscles):
    exercise = Exercise.objects.create(
        user=None,
        name="Plank",
        primary_muscle=muscles["Core"],
        tracking_type=Exercise.TrackingType.TIMED,
    )
    current = _current(user, exercise, target_seconds=90)

    assert progression.prefill(user, current, 1)["duration_seconds"] == 90


@pytest.mark.django_db
def test_increase_flag_is_true_when_every_planned_set_hits_the_rep_max(user, seeded_exercise):
    past = _past(user, seeded_exercise, date(2026, 11, 5), [(225, 8), (225, 8), (225, 8)])

    assert progression.increase_flag(past) is True


@pytest.mark.django_db
def test_increase_flag_is_false_when_one_set_falls_short(user, seeded_exercise):
    past = _past(user, seeded_exercise, date(2026, 11, 5), [(225, 8), (225, 7), (225, 8)])

    assert progression.increase_flag(past) is False


@pytest.mark.django_db
def test_increase_flag_ignores_extra_sets(user, seeded_exercise):
    past = _past(
        user,
        seeded_exercise,
        date(2026, 11, 5),
        [(225, 8), (225, 8)],
        planned_sets=2,
        extra_sets=[(225, 3)],
    )

    assert progression.increase_flag(past) is True


@pytest.mark.django_db
def test_increase_flag_ignores_missing_sets(user, seeded_exercise):
    past = _past(user, seeded_exercise, date(2026, 11, 5), [(225, 8)])
    past.planned_sets = 3
    past.save(update_fields=["planned_sets"])

    assert progression.increase_flag(past) is False


@pytest.mark.django_db
def test_increase_flag_is_false_without_a_rep_target(user, seeded_exercise):
    past = _past(user, seeded_exercise, date(2026, 11, 5), [(225, 8)])
    past.rep_max = None
    past.save(update_fields=["rep_max"])

    assert progression.increase_flag(past) is False


@pytest.mark.django_db
def test_increase_flag_is_false_for_timed_exercises(user, muscles):
    exercise = Exercise.objects.create(
        user=None,
        name="Plank",
        primary_muscle=muscles["Core"],
        tracking_type=Exercise.TrackingType.TIMED,
    )
    past = _past(user, exercise, date(2026, 11, 5), [(None, None)])

    assert progression.increase_flag(past) is False


@pytest.mark.django_db
def test_flag_for_upcoming_reads_the_last_completed_session(user, seeded_exercise):
    assert progression.flag_for_upcoming(user, seeded_exercise) is False

    _past(user, seeded_exercise, date(2026, 11, 5), [(225, 8), (225, 8), (225, 8)])

    assert progression.flag_for_upcoming(user, seeded_exercise) is True


@pytest.mark.django_db
def test_last_time_display_formats_weight_reps(user, seeded_exercise):
    _past(
        user,
        seeded_exercise,
        date(2026, 11, 5),
        [(225, 8), (225, 8), (225, 7)],
    )
    current = _current(user, seeded_exercise)

    assert progression.last_time_display(user, current) == "225×8, 225×8, 225×7"


@pytest.mark.django_db
def test_last_time_display_formats_bodyweight_reps(user, muscles):
    exercise = Exercise.objects.create(
        user=None,
        name="Pull-up",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.BODYWEIGHT,
    )
    _past(user, exercise, date(2026, 11, 5), [(None, 12), (None, 10)])
    current = _current(user, exercise)

    assert progression.last_time_display(user, current) == "12, 10"


@pytest.mark.django_db
def test_last_time_display_formats_timed_sets(user, muscles):
    exercise = Exercise.objects.create(
        user=None,
        name="Plank",
        primary_muscle=muscles["Core"],
        tracking_type=Exercise.TrackingType.TIMED,
    )
    past = _past(user, exercise, date(2026, 11, 5), [(None, None)])
    SetLog.objects.filter(session_exercise=past).update(duration_seconds=90)
    SetLog.objects.create(
        session_exercise=past,
        set_number=2,
        status=SetLog.Status.DONE,
        duration_seconds=45,
    )
    current = _current(user, exercise)

    assert progression.last_time_display(user, current) == "1:30, 45s"


@pytest.mark.django_db
def test_last_time_display_formats_cardio(user, muscles):
    exercise = Exercise.objects.create(
        user=None,
        name="Run",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.CARDIO,
    )
    past = _past(user, exercise, date(2026, 11, 5), [(None, None)])
    SetLog.objects.filter(session_exercise=past).update(
        duration_seconds=1800,
        distance_m=Decimal("4988.9664"),
    )
    current = _current(user, exercise)

    assert progression.last_time_display(user, current) == "30:00 · 3.1 mi"
