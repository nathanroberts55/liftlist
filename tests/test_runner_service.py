import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from freezegun import freeze_time

from apps.exercises.models import Exercise
from apps.plans.models import PlanItem, ScheduledWorkout
from apps.workouts.models import Session, SessionExercise, SetLog
from apps.workouts.services import runner

TODAY = date(2026, 11, 9)


def _exercise(muscles, name, tracking=Exercise.TrackingType.WEIGHT_REPS):
    return Exercise.objects.create(
        user=None,
        name=name,
        primary_muscle=muscles["Quads"],
        tracking_type=tracking,
    )


def _item(plan_day, exercise, order, **kwargs):
    defaults = {
        "target_sets": 3,
        "rep_min": 8,
        "rep_max": 10,
        "rest_seconds": 90,
    }
    defaults.update(kwargs)
    return PlanItem.objects.create(
        plan_day=plan_day,
        exercise=exercise,
        order=order,
        **defaults,
    )


def _scheduled(user, plan, plan_day, day=TODAY):
    return ScheduledWorkout.objects.create(
        user=user,
        plan=plan,
        plan_day=plan_day,
        scheduled_date=day,
    )


def _started(user, active_plan, active_plan_day, day=TODAY):
    workout = _scheduled(user, active_plan, active_plan_day, day)
    return runner.start_scheduled_session(user, workout), workout


def _log(session, session_exercise, *, weight="135", reps="8"):
    return runner.log_set(
        session,
        session_exercise,
        {"weight_lb": weight, "reps": reps},
    )


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_snapshots_targets_and_starts_in_progress(
    user, active_plan, active_plan_day, active_plan_item
):
    session, workout = _started(user, active_plan, active_plan_day)

    assert session.status == Session.Status.IN_PROGRESS
    assert session.kind == Session.Kind.SCHEDULED
    assert session.scheduled_workout_id == workout.pk
    assert session.plan_day_id == active_plan_day.pk
    assert session.performed_date == TODAY
    assert session.started_at is not None
    assert session.title == active_plan_day.name

    session_exercise = session.session_exercises.get()
    assert session_exercise.exercise_id == active_plan_item.exercise_id
    assert session_exercise.target_sets == 4
    assert session_exercise.planned_sets == 4
    assert session_exercise.rep_min == 6
    assert session_exercise.rep_max == 8
    assert session_exercise.rest_seconds == 120
    assert session_exercise.superset_group == ""

    # Past sessions keep their snapshot when the plan changes.
    active_plan_item.target_sets = 2
    active_plan_item.rep_max = 7
    active_plan_item.save(update_fields=["target_sets", "rep_max"])
    session_exercise.refresh_from_db()
    assert session_exercise.target_sets == 4
    assert session_exercise.rep_max == 8


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_rejects_a_second_in_progress_session(
    user, active_plan, active_plan_day, active_plan_item
):
    _started(user, active_plan, active_plan_day)
    second = _scheduled(user, active_plan, active_plan_day, day=date(2026, 11, 10))

    with pytest.raises(ValidationError):
        runner.start_scheduled_session(user, second)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_rejects_a_completed_workout(user, active_plan, active_plan_day, active_plan_item):
    workout = _scheduled(user, active_plan, active_plan_day)
    workout.status = ScheduledWorkout.Status.COMPLETED
    workout.save(update_fields=["status"])

    with pytest.raises(ValidationError):
        runner.start_scheduled_session(user, workout)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_rejects_another_users_workout(
    user, other_user, active_plan, active_plan_day, active_plan_item
):
    workout = _scheduled(user, active_plan, active_plan_day)

    with pytest.raises(ValidationError):
        runner.start_scheduled_session(other_user, workout)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_rejects_an_empty_day(user, active_plan, active_plan_day):
    workout = _scheduled(user, active_plan, active_plan_day)

    with pytest.raises(ValidationError):
        runner.start_scheduled_session(user, workout)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_next_step_walks_exercises_in_order(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    _item(active_plan_day, second_exercise, order=1, target_sets=2)
    session, _ = _started(user, active_plan, active_plan_day)

    first = session.session_exercises.get(exercise=seeded_exercise)
    second = session.session_exercises.get(exercise=second_exercise)

    step = runner.next_step(session)
    assert step.session_exercise.pk == first.pk
    assert step.set_number == 1
    assert step.is_superset is False
    assert step.rest_after_seconds == 120

    for _ in range(4):
        _log(session, first)

    step = runner.next_step(session)
    assert step.session_exercise.pk == second.pk
    assert step.set_number == 1

    _log(session, second)
    _log(session, second)
    assert runner.next_step(session) is None


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_next_step_rotates_supersets_and_rests_after_the_round(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    active_plan_item.superset_group = "A"
    active_plan_item.target_sets = 2
    active_plan_item.save(update_fields=["superset_group", "target_sets"])
    _item(
        active_plan_day,
        second_exercise,
        order=1,
        target_sets=2,
        superset_group="A",
    )
    session, _ = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)
    second = session.session_exercises.get(exercise=second_exercise)

    step = runner.next_step(session)
    assert (step.session_exercise.pk, step.set_number) == (first.pk, 1)
    assert step.is_superset is True
    assert step.superset_label == "A"
    assert step.round_number == 1
    assert step.total_rounds == 2
    assert step.rest_after_seconds == 0

    _log(session, first)
    step = runner.next_step(session)
    assert (step.session_exercise.pk, step.set_number) == (second.pk, 1)
    assert step.rest_after_seconds == 90

    _log(session, second)
    step = runner.next_step(session)
    assert (step.session_exercise.pk, step.set_number) == (first.pk, 2)
    assert step.rest_after_seconds == 0

    _log(session, first)
    step = runner.next_step(session)
    assert (step.session_exercise.pk, step.set_number) == (second.pk, 2)
    assert step.rest_after_seconds == 0

    _log(session, second)
    assert runner.next_step(session) is None


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_log_set_records_values_and_advances(user, active_plan, active_plan_day, active_plan_item):
    session, _ = _started(user, active_plan, active_plan_day)
    session_exercise = session.session_exercises.get()

    log = runner.log_set(
        session,
        session_exercise,
        {"weight_lb": "225", "reps": "8", "difficulty": "7", "client_id": "ignored"},
        client_id=uuid.uuid4(),
    )

    assert log.set_number == 1
    assert log.status == SetLog.Status.DONE
    assert log.weight_lb == 225
    assert log.reps == 8
    assert log.difficulty == 7
    assert log.is_extra is False
    assert session_exercise.next_set_number == 2
    assert session_exercise.status == SessionExercise.Status.IN_PROGRESS


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_log_set_is_idempotent_for_the_same_client_id(
    user, active_plan, active_plan_day, active_plan_item
):
    session, _ = _started(user, active_plan, active_plan_day)
    session_exercise = session.session_exercises.get()
    client_id = uuid.uuid4()

    first = runner.log_set(
        session,
        session_exercise,
        {"weight_lb": "225", "reps": "8"},
        client_id=client_id,
    )
    second = runner.log_set(
        session,
        session_exercise,
        {"weight_lb": "225", "reps": "8"},
        client_id=client_id,
    )

    assert first.pk == second.pk
    assert SetLog.objects.filter(session_exercise=session_exercise).count() == 1


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_log_set_rejects_a_client_id_from_another_exercise(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    _item(active_plan_day, second_exercise, order=1)
    session, _ = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)
    second = session.session_exercises.get(exercise=second_exercise)
    client_id = uuid.uuid4()
    _log(session, first)
    existing = SetLog.objects.get(session_exercise=first, set_number=1)
    existing.client_id = client_id
    existing.save(update_fields=["client_id"])

    with pytest.raises(ValidationError):
        runner.log_set(
            session,
            second,
            {"weight_lb": "135", "reps": "8"},
            client_id=client_id,
        )


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_log_set_rejects_invalid_input(user, active_plan, active_plan_day, active_plan_item):
    session, _ = _started(user, active_plan, active_plan_day)
    session_exercise = session.session_exercises.get()

    with pytest.raises(ValidationError):
        runner.log_set(session, session_exercise, {"weight_lb": "", "reps": "8"})
    with pytest.raises(ValidationError):
        runner.log_set(session, session_exercise, {"weight_lb": "225", "reps": ""})

    assert SetLog.objects.count() == 0


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_logging_a_finished_session_is_rejected(
    user, active_plan, active_plan_day, active_plan_item
):
    session, _ = _started(user, active_plan, active_plan_day)
    session_exercise = session.session_exercises.get()
    runner.finish_session(session)

    with pytest.raises(ValidationError):
        _log(session, session_exercise)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_skip_set_records_a_skipped_log(user, active_plan, active_plan_day, active_plan_item):
    session, _ = _started(user, active_plan, active_plan_day)
    session_exercise = session.session_exercises.get()

    log = runner.skip_set(session, session_exercise)

    assert log.status == SetLog.Status.SKIPPED
    assert log.set_number == 1
    assert session_exercise.next_set_number == 2
    assert session_exercise.logged_count == 1


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_skipping_every_set_marks_the_exercise_skipped(
    user, active_plan, active_plan_day, active_plan_item
):
    session, _ = _started(user, active_plan, active_plan_day)
    session_exercise = session.session_exercises.get()

    for _ in range(4):
        runner.skip_set(session, session_exercise)

    assert session_exercise.is_complete is True
    assert session_exercise.status == SessionExercise.Status.SKIPPED
    assert session_exercise.done_count == 0


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_add_set_extends_the_target_without_touching_the_plan(
    user, active_plan, active_plan_day, active_plan_item
):
    session, _ = _started(user, active_plan, active_plan_day)
    session_exercise = session.session_exercises.get()
    for _ in range(4):
        _log(session, session_exercise)
    assert session_exercise.status == SessionExercise.Status.DONE

    runner.add_set(session, session_exercise)

    session_exercise.refresh_from_db()
    active_plan_item.refresh_from_db()
    assert session_exercise.target_sets == 5
    assert session_exercise.status == SessionExercise.Status.IN_PROGRESS
    assert active_plan_item.target_sets == 4


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_skip_exercise_marks_remaining_sets_skipped(
    user, active_plan, active_plan_day, active_plan_item
):
    session, _ = _started(user, active_plan, active_plan_day)
    session_exercise = session.session_exercises.get()
    _log(session, session_exercise)

    runner.skip_exercise(session, session_exercise)

    session_exercise.refresh_from_db()
    assert session_exercise.status == SessionExercise.Status.SKIPPED
    assert session_exercise.done_count == 1
    assert (
        SetLog.objects.filter(
            session_exercise=session_exercise,
            status=SetLog.Status.SKIPPED,
        ).count()
        == 3
    )


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_add_exercise_uses_defaults_and_appends_to_the_session(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    extra = _exercise(muscles, "Cable Fly")
    session, _ = _started(user, active_plan, active_plan_day)

    session_exercise = runner.add_exercise(session, extra)

    assert session_exercise.exercise_id == extra.pk
    assert session_exercise.target_sets == 3
    assert session_exercise.planned_sets == 3
    assert session_exercise.rest_seconds == user.settings.default_rest_seconds
    assert session_exercise.order == 1
    assert session.session_exercises.count() == 2


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_add_exercise_rejects_zero_sets(
    user, active_plan, active_plan_day, active_plan_item, muscles
):
    extra = _exercise(muscles, "Cable Fly")
    session, _ = _started(user, active_plan, active_plan_day)

    with pytest.raises(ValidationError):
        runner.add_exercise(session, extra, target_sets=0)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_finish_fills_remaining_sets_and_completes_the_workout(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    _item(active_plan_day, second_exercise, order=1, target_sets=3)
    session, workout = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)
    second = session.session_exercises.get(exercise=second_exercise)
    _log(session, first)

    runner.finish_session(session)

    session.refresh_from_db()
    workout.refresh_from_db()
    assert session.status == Session.Status.COMPLETED
    assert session.completed_at is not None
    assert workout.status == ScheduledWorkout.Status.COMPLETED
    assert session.session_exercises.get(pk=first.pk).status == SessionExercise.Status.DONE
    assert session.session_exercises.get(pk=second.pk).status == SessionExercise.Status.SKIPPED
    assert SetLog.objects.filter(status=SetLog.Status.SKIPPED).count() == 6


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_finishing_a_catch_up_workout_marks_it_made_up(
    user, active_plan, active_plan_day, active_plan_item
):
    session, workout = _started(user, active_plan, active_plan_day, day=date(2026, 11, 2))

    runner.finish_session(session)

    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MADE_UP


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_finish_is_idempotent(user, active_plan, active_plan_day, active_plan_item):
    session, _ = _started(user, active_plan, active_plan_day)
    runner.finish_session(session)
    count = SetLog.objects.count()

    runner.finish_session(session)

    assert SetLog.objects.count() == count


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_discard_deletes_the_session_and_marks_a_past_workout_missed(
    user, active_plan, active_plan_day, active_plan_item
):
    session, workout = _started(user, active_plan, active_plan_day, day=date(2026, 11, 2))

    runner.discard_session(session, TODAY)

    assert Session.objects.filter(pk=session.pk).exists() is False
    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MISSED
    assert workout.marked_missed_manually is False


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_discard_restores_a_future_workout_to_pending(
    user, active_plan, active_plan_day, active_plan_item
):
    session, workout = _started(user, active_plan, active_plan_day, day=date(2026, 11, 16))

    runner.discard_session(session, TODAY)

    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.PENDING


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_discard_rejects_a_finished_session(user, active_plan, active_plan_day, active_plan_item):
    session, _ = _started(user, active_plan, active_plan_day)
    runner.finish_session(session)

    with pytest.raises(ValidationError):
        runner.discard_session(session, TODAY)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_reorder_moves_movable_blocks_below_locked_ones(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    third_exercise = _exercise(muscles, "Cable Fly")
    _item(active_plan_day, second_exercise, order=1, target_sets=1)
    _item(active_plan_day, third_exercise, order=2, target_sets=1)
    session, _ = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)
    second = session.session_exercises.get(exercise=second_exercise)
    third = session.session_exercises.get(exercise=third_exercise)
    for _ in range(4):
        _log(session, first)

    runner.reorder(session, [third.pk, second.pk])

    first.refresh_from_db()
    second.refresh_from_db()
    third.refresh_from_db()
    assert [first.order, third.order, second.order] == [0, 1, 2]
    assert runner.block_is_locked([first]) is True


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_reorder_keeps_superset_blocks_together(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    third_exercise = _exercise(muscles, "Cable Fly")
    active_plan_item.superset_group = "A"
    active_plan_item.save(update_fields=["superset_group"])
    _item(active_plan_day, second_exercise, order=1, superset_group="A")
    _item(active_plan_day, third_exercise, order=2)
    session, _ = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)
    second = session.session_exercises.get(exercise=second_exercise)
    third = session.session_exercises.get(exercise=third_exercise)

    runner.reorder(session, [third.pk, first.pk, second.pk])

    first.refresh_from_db()
    second.refresh_from_db()
    third.refresh_from_db()
    assert [third.order, first.order, second.order] == [0, 1, 2]


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_reorder_rejects_missing_exercises(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    _item(active_plan_day, second_exercise, order=1)
    session, _ = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)

    with pytest.raises(ValidationError):
        runner.reorder(session, [first.pk])


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_move_exercise_swaps_adjacent_blocks(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    third_exercise = _exercise(muscles, "Cable Fly")
    _item(active_plan_day, second_exercise, order=1)
    _item(active_plan_day, third_exercise, order=2)
    session, _ = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)
    second = session.session_exercises.get(exercise=second_exercise)
    third = session.session_exercises.get(exercise=third_exercise)

    assert runner.move_exercise(session, second, "up") is True
    first.refresh_from_db()
    second.refresh_from_db()
    assert [second.order, first.order, third.order] == [0, 1, 2]

    assert runner.move_exercise(session, second, "down") is True
    first.refresh_from_db()
    second.refresh_from_db()
    assert [first.order, second.order, third.order] == [0, 1, 2]

    assert runner.move_exercise(session, first, "up") is False


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_move_exercise_cannot_cross_a_completed_block(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    _item(active_plan_day, second_exercise, order=1)
    session, _ = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)
    second = session.session_exercises.get(exercise=second_exercise)
    for _ in range(4):
        _log(session, first)

    with pytest.raises(ValidationError):
        runner.move_exercise(session, second, "up")


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_jump_places_the_exercise_after_the_last_started_block(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    third_exercise = _exercise(muscles, "Cable Fly")
    _item(active_plan_day, second_exercise, order=1)
    _item(active_plan_day, third_exercise, order=2)
    session, _ = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)
    second = session.session_exercises.get(exercise=second_exercise)
    third = session.session_exercises.get(exercise=third_exercise)
    _log(session, first)

    runner.jump_to(session, third)

    first.refresh_from_db()
    second.refresh_from_db()
    third.refresh_from_db()
    assert [first.order, third.order, second.order] == [0, 1, 2]


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_jump_rejects_a_completed_exercise(
    user, active_plan, active_plan_day, active_plan_item, seeded_exercise, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    _item(active_plan_day, second_exercise, order=1)
    session, _ = _started(user, active_plan, active_plan_day)
    first = session.session_exercises.get(exercise=seeded_exercise)
    for _ in range(4):
        _log(session, first)

    with pytest.raises(ValidationError):
        runner.jump_to(session, first)


def test_validate_weight_reps_requires_weight_and_reps():
    with pytest.raises(ValidationError):
        runner.validate_set_fields(Exercise.TrackingType.WEIGHT_REPS, {"reps": "8"})
    with pytest.raises(ValidationError):
        runner.validate_set_fields(Exercise.TrackingType.WEIGHT_REPS, {"weight_lb": "225"})

    values = runner.validate_set_fields(
        Exercise.TrackingType.WEIGHT_REPS,
        {"weight_lb": "225", "reps": "8", "difficulty": "7"},
    )
    assert values == {
        "weight_lb": 225,
        "reps": 8,
        "duration_seconds": None,
        "distance_mi": None,
        "difficulty": 7,
    }


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"weight_lb": "-5", "reps": "8"}, "negative"),
        ({"weight_lb": "10000", "reps": "8"}, "large"),
        ({"weight_lb": "225", "reps": "0"}, "at least"),
        ({"weight_lb": "225", "reps": "1001"}, "at most"),
        ({"weight_lb": "225", "reps": "8", "difficulty": "11"}, "at most"),
        ({"weight_lb": "abc", "reps": "8"}, "valid"),
    ],
)
def test_validate_weight_reps_rejects_bad_values(data, message):
    with pytest.raises(ValidationError) as error:
        runner.validate_set_fields(Exercise.TrackingType.WEIGHT_REPS, data)

    assert message in error.value.messages[0]


def test_validate_bodyweight_needs_only_reps():
    values = runner.validate_set_fields(
        Exercise.TrackingType.BODYWEIGHT,
        {"reps": "12", "weight_lb": "25"},
    )

    assert values["reps"] == 12
    assert values["weight_lb"] == 25
    assert values["duration_seconds"] is None


def test_validate_timed_accepts_seconds_or_mmss():
    values = runner.validate_set_fields(
        Exercise.TrackingType.TIMED,
        {"duration_seconds": "90"},
    )
    assert values["duration_seconds"] == 90

    values = runner.validate_set_fields(
        Exercise.TrackingType.TIMED,
        {"duration": "1:30"},
    )
    assert values["duration_seconds"] == 90

    with pytest.raises(ValidationError):
        runner.validate_set_fields(Exercise.TrackingType.TIMED, {"duration": "1:60"})
    with pytest.raises(ValidationError):
        runner.validate_set_fields(Exercise.TrackingType.TIMED, {"duration": "soon"})


def test_validate_cardio_parses_duration_and_distance():
    values = runner.validate_set_fields(
        Exercise.TrackingType.CARDIO,
        {"duration": "30:00", "distance_mi": "3.1"},
    )

    assert values["duration_seconds"] == 1800
    assert values["distance_mi"] == Decimal("3.10")
    assert values["weight_lb"] is None
    assert values["reps"] is None


def test_validate_cardio_accepts_distance_only():
    values = runner.validate_set_fields(
        Exercise.TrackingType.CARDIO,
        {"distance_mi": "2.48"},
    )

    assert values["duration_seconds"] is None
    assert values["distance_mi"] == Decimal("2.48")


def test_validate_cardio_accepts_duration_only():
    values = runner.validate_set_fields(
        Exercise.TrackingType.CARDIO,
        {"duration": "45:00"},
    )

    assert values["duration_seconds"] == 2700
    assert values["distance_mi"] is None


def test_validate_cardio_requires_duration_or_distance():
    with pytest.raises(ValidationError):
        runner.validate_set_fields(Exercise.TrackingType.CARDIO, {})
    with pytest.raises(ValidationError):
        runner.validate_set_fields(Exercise.TrackingType.CARDIO, {"distance_mi": ""})


def test_validate_weight_distance_requires_weight_but_distance_is_optional():
    values = runner.validate_set_fields(
        Exercise.TrackingType.WEIGHT_DISTANCE,
        {"weight_lb": "100"},
    )
    assert values["weight_lb"] == 100
    assert values["distance_mi"] is None

    with pytest.raises(ValidationError):
        runner.validate_set_fields(Exercise.TrackingType.WEIGHT_DISTANCE, {})
