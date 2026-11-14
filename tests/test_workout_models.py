from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.workouts.models import Session, SessionExercise, SetLog, Tag

TODAY = date(2026, 11, 9)


def _session(user, **kwargs):
    defaults = {
        "kind": Session.Kind.SCHEDULED,
        "title": "Test workout",
        "performed_date": TODAY,
        "status": Session.Status.IN_PROGRESS,
    }
    defaults.update(kwargs)
    return Session.objects.create(user=user, **defaults)


def _exercise(session, exercise, **kwargs):
    defaults = {
        "session": session,
        "exercise": exercise,
        "order": 0,
        "target_sets": 3,
        "planned_sets": 3,
        "rest_seconds": 90,
    }
    defaults.update(kwargs)
    return SessionExercise.objects.create(**defaults)


@pytest.mark.django_db
def test_tag_names_are_case_insensitive_per_user(user):
    Tag.objects.create(user=user, name="Push")

    with pytest.raises(IntegrityError), transaction.atomic():
        Tag.objects.create(user=user, name="push")


@pytest.mark.django_db
def test_tags_can_repeat_across_users(user, other_user):
    Tag.objects.create(user=user, name="Push")
    Tag.objects.create(user=other_user, name="push")

    assert Tag.objects.filter(user=user).count() == Tag.objects.filter(user=other_user).count() == 1


@pytest.mark.django_db
def test_only_one_in_progress_session_per_user(user):
    _session(user)

    with pytest.raises(IntegrityError), transaction.atomic():
        _session(user)


@pytest.mark.django_db
def test_completed_sessions_do_not_block_a_new_in_progress_session(user):
    _session(user, status=Session.Status.COMPLETED, completed_at=timezone.now())
    _session(user)

    assert Session.objects.filter(user=user).count() == 2


@pytest.mark.django_db
def test_two_users_can_each_have_an_in_progress_session(user, other_user):
    _session(user)
    _session(other_user)

    assert Session.objects.filter(status=Session.Status.IN_PROGRESS).count() == 2


@pytest.mark.django_db
def test_set_numbers_are_unique_per_session_exercise(user, seeded_exercise):
    session = _session(user)
    session_exercise = _exercise(session, seeded_exercise)
    SetLog.objects.create(session_exercise=session_exercise, set_number=1, reps=8)

    with pytest.raises(IntegrityError), transaction.atomic():
        SetLog.objects.create(session_exercise=session_exercise, set_number=1, reps=8)


@pytest.mark.django_db
def test_session_exercise_counts_sets_and_completion(user, seeded_exercise):
    session = _session(user)
    session_exercise = _exercise(session, seeded_exercise, target_sets=3)
    SetLog.objects.create(session_exercise=session_exercise, set_number=1, reps=8)
    SetLog.objects.create(session_exercise=session_exercise, set_number=2, reps=7)

    assert session_exercise.logged_count == 2
    assert session_exercise.done_count == 2
    assert session_exercise.next_set_number == 3
    assert session_exercise.is_complete is False

    SetLog.objects.create(session_exercise=session_exercise, set_number=3, reps=6)
    assert session_exercise.is_complete is True


@pytest.mark.django_db
def test_skipped_exercise_is_complete(user, seeded_exercise):
    session = _session(user)
    session_exercise = _exercise(session, seeded_exercise, status=SessionExercise.Status.SKIPPED)

    assert session_exercise.is_complete is True


@pytest.mark.django_db
def test_session_progress_and_elapsed_labels(user, seeded_exercise):
    started = timezone.now() - timedelta(seconds=95)
    session = _session(user, started_at=started, completed_at=timezone.now())
    first = _exercise(session, seeded_exercise, order=0, target_sets=4)
    _exercise(session, seeded_exercise, order=1, target_sets=3)
    SetLog.objects.create(session_exercise=first, set_number=1, weight_lb=225, reps=8)

    assert session.done_set_count == 1
    assert session.target_set_count == 7
    assert session.progress_label == "1 of 7 sets"
    assert session.elapsed_seconds in (94, 95, 96)
    assert session.elapsed_label.startswith("1:3")


@pytest.mark.django_db
def test_session_exercise_target_labels_for_weight_reps(user, seeded_exercise):
    session = _session(user)
    session_exercise = _exercise(session, seeded_exercise, target_sets=4, rep_min=6, rep_max=8)

    assert session_exercise.target_summary == "4 × 6–8"
    assert session_exercise.goal_label == "Goal 6–8 reps"


@pytest.mark.django_db
def test_session_exercise_target_labels_for_timed(user, muscles):
    exercise = Exercise.objects.create(
        user=None,
        name="Plank",
        primary_muscle=muscles["Core"],
        tracking_type=Exercise.TrackingType.TIMED,
    )
    session = _session(user)
    session_exercise = _exercise(session, exercise, target_sets=3, target_seconds=90)

    assert session_exercise.target_summary == "3 × 1:30"
    assert session_exercise.goal_label == "Goal 1:30"


@pytest.mark.django_db
def test_session_exercise_target_labels_for_cardio(user, muscles):
    exercise = Exercise.objects.create(
        user=None,
        name="Run",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.CARDIO,
    )
    session = _session(user)
    session_exercise = _exercise(
        session,
        exercise,
        target_sets=1,
        target_seconds=1800,
        target_distance_m=Decimal("4988.9664"),
        distance_unit="MI",
    )

    assert session_exercise.target_summary == "30:00 · 3.1 mi"
    assert session_exercise.goal_label == "Goal 30:00 · 3.1 mi"


@pytest.mark.django_db
def test_session_exercise_target_labels_for_distance(user, muscles):
    exercise = Exercise.objects.create(
        user=None,
        name="Sled Push",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.DISTANCE,
        default_distance_unit="YD",
    )
    session = _session(user)
    session_exercise = _exercise(
        session,
        exercise,
        target_sets=4,
        target_distance_m=Decimal("13.7160"),
        distance_unit="YD",
    )

    assert session_exercise.target_summary == "4 × 15 yd"
    assert session_exercise.goal_label == "Goal 15 yd"


@pytest.mark.django_db
def test_set_display_values_for_each_tracking_type(user, muscles, seeded_exercise):
    session = _session(user)
    weight_reps = _exercise(session, seeded_exercise, order=0)
    bodyweight_exercise = Exercise.objects.create(
        user=None,
        name="Pull-up",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.BODYWEIGHT,
    )
    timed_exercise = Exercise.objects.create(
        user=None,
        name="Plank",
        primary_muscle=muscles["Core"],
        tracking_type=Exercise.TrackingType.TIMED,
    )
    cardio_exercise = Exercise.objects.create(
        user=None,
        name="Run",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.CARDIO,
    )
    distance_exercise = Exercise.objects.create(
        user=None,
        name="Sled Push",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.DISTANCE,
        default_distance_unit="YD",
    )
    bodyweight = _exercise(session, bodyweight_exercise, order=1)
    timed = _exercise(session, timed_exercise, order=2)
    cardio = _exercise(session, cardio_exercise, order=3)
    distance = _exercise(session, distance_exercise, order=4, distance_unit="YD")

    assert (
        SetLog.objects.create(
            session_exercise=weight_reps, set_number=1, weight_lb=225, reps=8
        ).display_value
        == "225 × 8"
    )
    assert (
        SetLog.objects.create(
            session_exercise=bodyweight, set_number=1, weight_lb=25, reps=12
        ).display_value
        == "12 (+25 lb)"
    )
    assert (
        SetLog.objects.create(
            session_exercise=timed, set_number=1, duration_seconds=60
        ).display_value
        == "1:00"
    )
    assert (
        SetLog.objects.create(
            session_exercise=cardio,
            set_number=1,
            duration_seconds=1800,
            distance_m=Decimal("4988.9664"),
        ).display_value
        == "30:00 · 3.1 mi"
    )
    assert (
        SetLog.objects.create(
            session_exercise=distance,
            set_number=1,
            weight_lb=100,
            reps=30,
            distance_m=Decimal("13.7160"),
        ).display_value
        == "100 lb · 30 steps · 15 yd"
    )
