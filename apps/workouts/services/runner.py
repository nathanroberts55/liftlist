"""Workout runner services (F-05).

The runner is a small state machine over ``SessionExercise`` rows and their
``SetLog`` children. Views parse input, call these functions, and render.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.services.settings import get_settings
from apps.exercises.models import DistanceUnit, Exercise
from apps.exercises.services import units as distance_units
from apps.plans.services import scheduling

from ..models import Session, SessionExercise, SetLog


@dataclass(frozen=True)
class Step:
    """The next thing the runner should show."""

    session_exercise: SessionExercise
    set_number: int
    is_superset: bool = False
    superset_label: str = ""
    round_number: int = 1
    total_rounds: int = 1
    rest_after_seconds: int = 0


# --- Step engine ------------------------------------------------------------


def _blocks(exercises) -> list[list[SessionExercise]]:
    """Group contiguous rows that share a non-blank superset label."""
    blocks: list[list[SessionExercise]] = []
    current: list[SessionExercise] = []
    for exercise in exercises:
        if (
            current
            and exercise.superset_group
            and exercise.superset_group == current[-1].superset_group
        ):
            current.append(exercise)
        else:
            if current:
                blocks.append(current)
            current = [exercise]
    if current:
        blocks.append(current)
    return blocks


def remaining_sets(session_exercise: SessionExercise) -> int:
    if session_exercise.status == SessionExercise.Status.SKIPPED:
        return 0
    return max(0, session_exercise.target_sets - session_exercise.logged_count)


def _remaining_sets(exercises) -> int:
    return sum(remaining_sets(exercise) for exercise in exercises)


def _exercise_position(session: Session, session_exercise: SessionExercise) -> tuple[int, int]:
    exercises = list(session.session_exercises.all())
    total = len(exercises)
    for index, exercise in enumerate(exercises, start=1):
        if exercise.pk == session_exercise.pk:
            return index, total
    return 1, total or 1


def next_step(session: Session) -> Step | None:
    """Return the next set to perform, or ``None`` when everything is logged."""
    exercises = list(
        session.session_exercises.select_related("exercise")
        .prefetch_related("sets")
        .order_by("order", "pk")
    )
    if not exercises:
        return None

    remaining_total = _remaining_sets(exercises)
    for block in _blocks(exercises):
        active = [exercise for exercise in block if not exercise.is_complete]
        if not active:
            continue

        is_last = remaining_total <= 1
        label = block[0].superset_group if len(block) > 1 else ""

        if not label:
            exercise = block[0]
            return Step(
                session_exercise=exercise,
                set_number=exercise.next_set_number,
                rest_after_seconds=0 if is_last else exercise.rest_seconds,
            )

        round_number = min(exercise.next_set_number for exercise in active)
        candidate = next(
            exercise for exercise in active if exercise.next_set_number == round_number
        )
        finishes_round = all(
            exercise.next_set_number > round_number
            for exercise in active
            if exercise.pk != candidate.pk
        )
        rest = block[-1].rest_seconds if finishes_round else 0
        if is_last:
            rest = 0
        return Step(
            session_exercise=candidate,
            set_number=candidate.next_set_number,
            is_superset=True,
            superset_label=label,
            round_number=round_number,
            total_rounds=max(exercise.target_sets for exercise in block),
            rest_after_seconds=rest,
        )
    return None


def step_context(session: Session, step: Step | None) -> dict:
    """Display data for one step. Kept here so views stay thin."""
    if step is None:
        return {}
    position, total = _exercise_position(session, step.session_exercise)
    return {
        "step": step,
        "tracking_type": step.session_exercise.exercise.tracking_type,
        "exercise_position": position,
        "exercise_total": total,
        "remaining_sets": remaining_sets(step.session_exercise),
    }


# --- Starting and finishing -------------------------------------------------


@transaction.atomic
def start_scheduled_session(user, scheduled_workout) -> Session:
    """Snapshot a Scheduled Workout's items into a new in-progress Session."""
    if scheduled_workout.user_id != user.pk:
        raise ValidationError("That workout does not belong to you.")
    if scheduled_workout.status in (
        scheduled_workout.Status.COMPLETED,
        scheduled_workout.Status.MADE_UP,
    ):
        raise ValidationError("That workout is already complete.")
    if Session.objects.filter(user=user, status=Session.Status.IN_PROGRESS).exists():
        raise ValidationError("Finish or discard your current workout first.")
    if Session.objects.filter(scheduled_workout=scheduled_workout).exists():
        raise ValidationError("That workout already has a session.")

    items = list(
        scheduled_workout.plan_day.items.select_related("exercise").order_by("order", "pk")
    )
    if not items:
        raise ValidationError("This day has no exercises yet.")

    now = timezone.now()
    session = Session.objects.create(
        user=user,
        kind=Session.Kind.SCHEDULED,
        scheduled_workout=scheduled_workout,
        plan_day=scheduled_workout.plan_day,
        title=scheduled_workout.plan_day.name,
        performed_date=timezone.localdate(),
        status=Session.Status.IN_PROGRESS,
        started_at=now,
    )
    SessionExercise.objects.bulk_create(
        [
            SessionExercise(
                session=session,
                exercise=item.exercise,
                plan_item=item,
                order=item.order,
                superset_group=item.superset_group,
                target_sets=item.target_sets,
                planned_sets=item.target_sets,
                rep_min=item.rep_min,
                rep_max=item.rep_max,
                target_seconds=item.target_seconds,
                target_distance_m=item.target_distance_m,
                distance_unit=item.distance_unit,
                rest_seconds=item.rest_seconds,
            )
            for item in items
        ]
    )
    return session


def _ensure_in_progress(session: Session) -> None:
    if not session.is_in_progress:
        raise ValidationError("This workout is already finished.")


def _ensure_belongs(session: Session, session_exercise: SessionExercise) -> None:
    if session_exercise.session_id != session.pk:
        raise ValidationError("That exercise is not part of this workout.")


def refresh_status(session_exercise: SessionExercise) -> None:
    logs = list(session_exercise.sets.all())
    if len(logs) < session_exercise.target_sets:
        status = SessionExercise.Status.IN_PROGRESS
    elif any(log.status == SetLog.Status.DONE for log in logs):
        status = SessionExercise.Status.DONE
    else:
        status = SessionExercise.Status.SKIPPED
    if session_exercise.status != status:
        session_exercise.status = status
        session_exercise.save(update_fields=["status", "updated_at"])


def _existing_log(client_id) -> SetLog | None:
    if not client_id:
        return None
    return SetLog.objects.filter(client_id=client_id).first()


def _idempotent_log(session_exercise: SessionExercise, client_id) -> SetLog | None:
    existing = _existing_log(client_id)
    if existing is None:
        return None
    if existing.session_exercise_id != session_exercise.pk:
        raise ValidationError("That save key belongs to another set.")
    return existing


@transaction.atomic
def log_set(
    session: Session,
    session_exercise: SessionExercise,
    data,
    client_id=None,
) -> SetLog:
    """Validate and store one completed set. Duplicate ``client_id`` is a no-op."""
    _ensure_in_progress(session)
    _ensure_belongs(session, session_exercise)
    existing = _idempotent_log(session_exercise, client_id)
    if existing is not None:
        return existing

    values = validate_set_fields(
        session_exercise.exercise.tracking_type,
        data,
        distance_unit=session_exercise.distance_unit,
    )
    set_number = session_exercise.next_set_number
    log = SetLog.objects.create(
        session_exercise=session_exercise,
        set_number=set_number,
        status=SetLog.Status.DONE,
        is_extra=set_number > session_exercise.planned_sets,
        client_id=client_id or uuid.uuid4(),
        completed_at=timezone.now(),
        **values,
    )
    refresh_status(session_exercise)
    return log


@transaction.atomic
def skip_set(session: Session, session_exercise: SessionExercise, client_id=None) -> SetLog:
    """Record the next set as skipped."""
    _ensure_in_progress(session)
    _ensure_belongs(session, session_exercise)
    existing = _idempotent_log(session_exercise, client_id)
    if existing is not None:
        return existing

    set_number = session_exercise.next_set_number
    log = SetLog.objects.create(
        session_exercise=session_exercise,
        set_number=set_number,
        status=SetLog.Status.SKIPPED,
        is_extra=set_number > session_exercise.planned_sets,
        client_id=client_id or uuid.uuid4(),
        completed_at=timezone.now(),
    )
    refresh_status(session_exercise)
    return log


@transaction.atomic
def add_set(session: Session, session_exercise: SessionExercise) -> SessionExercise:
    """Add one set to this session's exercise (never the plan)."""
    _ensure_in_progress(session)
    _ensure_belongs(session, session_exercise)
    session_exercise.target_sets += 1
    if session_exercise.status in (
        SessionExercise.Status.DONE,
        SessionExercise.Status.SKIPPED,
    ):
        session_exercise.status = SessionExercise.Status.IN_PROGRESS
    session_exercise.save(update_fields=["target_sets", "status", "updated_at"])
    return session_exercise


@transaction.atomic
def skip_exercise(session: Session, session_exercise: SessionExercise) -> SessionExercise:
    """Mark every remaining planned set as skipped."""
    _ensure_in_progress(session)
    _ensure_belongs(session, session_exercise)
    start = session_exercise.next_set_number
    logs = [
        SetLog(
            session_exercise=session_exercise,
            set_number=number,
            status=SetLog.Status.SKIPPED,
            is_extra=number > session_exercise.planned_sets,
            completed_at=timezone.now(),
        )
        for number in range(start, session_exercise.target_sets + 1)
    ]
    if logs:
        SetLog.objects.bulk_create(logs)
    session_exercise.status = SessionExercise.Status.SKIPPED
    session_exercise.save(update_fields=["status", "updated_at"])
    return session_exercise


@transaction.atomic
def add_exercise(
    session: Session,
    exercise: Exercise,
    *,
    target_sets: int = 3,
    rep_min=None,
    rep_max=None,
    target_seconds=None,
    target_distance_m=None,
    distance_unit=None,
    rest_seconds=None,
) -> SessionExercise:
    """Add a spur-of-the-moment exercise to this session only."""
    _ensure_in_progress(session)
    if target_sets < 1:
        raise ValidationError("Use at least one set.")
    if rest_seconds is None:
        rest_seconds = get_settings(session.user).default_rest_seconds
    if distance_unit is None:
        distance_unit = exercise.default_distance_unit
    order = session.session_exercises.order_by("-order").values_list("order", flat=True).first()
    session_exercise = SessionExercise.objects.create(
        session=session,
        exercise=exercise,
        order=(order + 1) if order is not None else 0,
        target_sets=target_sets,
        planned_sets=target_sets,
        rep_min=rep_min,
        rep_max=rep_max,
        target_seconds=target_seconds,
        target_distance_m=target_distance_m,
        distance_unit=distance_unit,
        rest_seconds=rest_seconds,
    )
    return session_exercise


# --- Ordering ---------------------------------------------------------------


def exercise_blocks(session: Session) -> list[list[SessionExercise]]:
    """Group a session's exercises for the reorder sheet."""
    exercises = list(
        session.session_exercises.select_related("exercise")
        .prefetch_related("sets")
        .order_by("order", "pk")
    )
    return _blocks(exercises)


def block_is_locked(block: list[SessionExercise]) -> bool:
    return _block_is_locked(block)


def _save_block_order(blocks: list[list[SessionExercise]]) -> list[SessionExercise]:
    ordered = [exercise for block in blocks for exercise in block]
    for index, exercise in enumerate(ordered):
        if exercise.order != index:
            exercise.order = index
            exercise.save(update_fields=["order", "updated_at"])
    return ordered


def _block_is_locked(block: list[SessionExercise]) -> bool:
    return any(
        exercise.status in (SessionExercise.Status.DONE, SessionExercise.Status.SKIPPED)
        or exercise.is_complete
        for exercise in block
    )


@transaction.atomic
def reorder(session: Session, ordered_ids) -> list[SessionExercise]:
    """Reorder movable exercises; completed blocks stay at the top."""
    _ensure_in_progress(session)
    exercises = list(
        session.session_exercises.select_related("exercise")
        .prefetch_related("sets")
        .order_by("order", "pk")
    )
    blocks = _blocks(exercises)
    locked = [block for block in blocks if _block_is_locked(block)]
    movable = [block for block in blocks if not _block_is_locked(block)]

    try:
        ids = [int(value) for value in ordered_ids]
    except (TypeError, ValueError) as error:
        raise ValidationError("That order is not valid.") from error

    movable_ids = {exercise.pk for block in movable for exercise in block}
    if len(ids) != len(movable_ids) or set(ids) != movable_ids:
        raise ValidationError("Include every remaining exercise once.")

    by_id = {exercise.pk: block for block in movable for exercise in block}
    requested: list[list[SessionExercise]] = []
    seen: set[int] = set()
    for exercise_id in ids:
        block = by_id.get(exercise_id)
        if block is None or id(block) in seen:
            continue
        seen.add(id(block))
        requested.append(block)

    return _save_block_order(locked + requested)


@transaction.atomic
def move_exercise(session: Session, session_exercise: SessionExercise, direction: str) -> bool:
    """Move a block one position with the ▲▼ fallback."""
    _ensure_in_progress(session)
    _ensure_belongs(session, session_exercise)
    exercises = list(
        session.session_exercises.select_related("exercise")
        .prefetch_related("sets")
        .order_by("order", "pk")
    )
    blocks = _blocks(exercises)
    index = next(
        (
            position
            for position, block in enumerate(blocks)
            if any(exercise.pk == session_exercise.pk for exercise in block)
        ),
        None,
    )
    if index is None:
        raise ValidationError("That exercise is not part of this workout.")
    if _block_is_locked(blocks[index]):
        raise ValidationError("Completed exercises stay at the top.")

    if direction not in ("up", "down"):
        raise ValidationError("Choose a direction.")
    target = index - 1 if direction == "up" else index + 1
    if target < 0 or target >= len(blocks):
        return False
    if _block_is_locked(blocks[target]):
        raise ValidationError("Completed exercises stay at the top.")

    blocks[index], blocks[target] = blocks[target], blocks[index]
    _save_block_order(blocks)
    return True


@transaction.atomic
def jump_to(session: Session, session_exercise: SessionExercise) -> list[SessionExercise]:
    """Move a block directly after the last exercise that has been started."""
    _ensure_in_progress(session)
    _ensure_belongs(session, session_exercise)
    exercises = list(
        session.session_exercises.select_related("exercise")
        .prefetch_related("sets")
        .order_by("order", "pk")
    )
    blocks = _blocks(exercises)
    target_index = next(
        (
            position
            for position, block in enumerate(blocks)
            if any(exercise.pk == session_exercise.pk for exercise in block)
        ),
        None,
    )
    if target_index is None:
        raise ValidationError("That exercise is not part of this workout.")
    if _block_is_locked(blocks[target_index]):
        raise ValidationError("Completed exercises stay at the top.")

    target = blocks.pop(target_index)
    insert_at = 0
    for position, block in enumerate(blocks):
        started = any(
            exercise.status
            in (
                SessionExercise.Status.IN_PROGRESS,
                SessionExercise.Status.DONE,
                SessionExercise.Status.SKIPPED,
            )
            or exercise.logged_count > 0
            for exercise in block
        )
        if started:
            insert_at = position + 1
    blocks.insert(insert_at, target)
    return _save_block_order(blocks)


# --- Validation -------------------------------------------------------------


def _value(data, key):
    value = data.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _decimal(
    data,
    key,
    label,
    *,
    required=False,
    maximum=Decimal("9999.99"),
    quantum=Decimal("0.01"),
) -> Decimal | None:
    raw = _value(data, key)
    if raw is None:
        if required:
            raise ValidationError(f"Enter {label}.")
        return None
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError) as error:
        raise ValidationError(f"Enter a valid {label}.") from error
    if number < 0:
        raise ValidationError(f"{label.capitalize()} cannot be negative.")
    if number > maximum:
        raise ValidationError(f"{label.capitalize()} is too large.")
    return number.quantize(quantum)


def _integer(
    data,
    key,
    label,
    *,
    required=False,
    minimum=1,
    maximum=None,
) -> int | None:
    raw = _value(data, key)
    if raw is None:
        if required:
            raise ValidationError(f"Enter {label}.")
        return None
    try:
        number = int(raw)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"Enter a valid {label}.") from error
    if number < minimum:
        raise ValidationError(f"{label.capitalize()} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{label.capitalize()} must be at most {maximum}.")
    return number


def _parse_duration(data):
    """Accept ``duration_seconds`` or a ``mm:ss`` ``duration`` string."""
    seconds = _value(data, "duration_seconds")
    if seconds is not None:
        return _integer(data, "duration_seconds", "duration", required=True, maximum=86400)
    raw = _value(data, "duration")
    if raw is None:
        return None
    if ":" in raw:
        parts = raw.split(":")
        if len(parts) != 2:
            raise ValidationError("Enter the duration as mm:ss.")
        try:
            minutes, remainder = int(parts[0]), int(parts[1])
        except ValueError as error:
            raise ValidationError("Enter the duration as mm:ss.") from error
        if minutes < 0 or remainder < 0 or remainder >= 60:
            raise ValidationError("Enter the duration as mm:ss.")
        return minutes * 60 + remainder
    try:
        return int(raw)
    except ValueError as error:
        raise ValidationError("Enter a duration.") from error


def validate_set_fields(
    tracking_type: str,
    data,
    *,
    distance_unit=DistanceUnit.MILES,
) -> dict:
    """Validate a set payload per tracking type (PRD §8.2).

    ``distance`` arrives in the session exercise's display unit and is stored
    canonically in metres.
    """
    weight = _decimal(data, "weight_lb", "weight")
    reps_label = "steps" if tracking_type == Exercise.TrackingType.DISTANCE else "reps"
    reps = _integer(data, "reps", reps_label, maximum=1000)
    duration = _parse_duration(data)
    distance = _decimal(
        data,
        "distance",
        "distance",
        maximum=Decimal("16093440"),
        quantum=Decimal("0.0001"),
    )
    distance_m = distance_units.to_meters(distance, distance_unit) if distance is not None else None
    difficulty = _integer(data, "difficulty", "difficulty", minimum=1, maximum=10)

    if tracking_type == Exercise.TrackingType.WEIGHT_REPS:
        if weight is None:
            raise ValidationError("Enter weight.")
        if reps is None:
            raise ValidationError("Enter reps.")
        duration = distance_m = None
    elif tracking_type == Exercise.TrackingType.BODYWEIGHT:
        if reps is None:
            raise ValidationError("Enter reps.")
        duration = distance_m = None
    elif tracking_type == Exercise.TrackingType.TIMED:
        if duration is None:
            raise ValidationError("Enter duration.")
        if duration < 1:
            raise ValidationError("Duration must be at least 1 second.")
        distance_m = None
        reps = None
    elif tracking_type == Exercise.TrackingType.CARDIO:
        if duration is not None and duration < 1:
            duration = None
        if distance_m is not None and distance_m <= 0:
            distance_m = None
        if duration is None and distance_m is None:
            raise ValidationError("Enter a duration or a distance.")
        weight = None
        reps = None
    elif tracking_type == Exercise.TrackingType.DISTANCE:
        if distance_m is not None and distance_m <= 0:
            distance_m = None
        if distance_m is None and reps is None:
            raise ValidationError("Enter a distance or steps.")
        duration = None
    else:
        raise ValidationError("Unsupported tracking type.")

    return {
        "weight_lb": weight,
        "reps": reps,
        "duration_seconds": duration,
        "distance_m": distance_m,
        "difficulty": difficulty,
    }


# --- Finish and discard -----------------------------------------------------


@transaction.atomic
def finish_session(session: Session, now=None) -> Session:
    """Complete the session and fill any remaining planned sets as skipped."""
    if session.is_completed:
        return session
    now = now or timezone.now()
    exercises = list(session.session_exercises.prefetch_related("sets").order_by("order", "pk"))
    for exercise in exercises:
        remaining = remaining_sets(exercise)
        if remaining:
            start = exercise.next_set_number
            SetLog.objects.bulk_create(
                [
                    SetLog(
                        session_exercise=exercise,
                        set_number=number,
                        status=SetLog.Status.SKIPPED,
                        is_extra=number > exercise.planned_sets,
                        completed_at=now,
                    )
                    for number in range(start, start + remaining)
                ]
            )
        if exercise.status == SessionExercise.Status.SKIPPED:
            continue
        if exercise.done_count:
            exercise.status = SessionExercise.Status.DONE
        else:
            exercise.status = SessionExercise.Status.SKIPPED
        exercise.save(update_fields=["status", "updated_at"])

    session.status = Session.Status.COMPLETED
    session.completed_at = now
    session.save(update_fields=["status", "completed_at", "updated_at"])
    if session.scheduled_workout_id:
        scheduling.resolve_status_on_complete(
            session.scheduled_workout,
            session.performed_date,
        )
    return session


@transaction.atomic
def discard_session(session: Session, today=None) -> None:
    """Hard delete an in-progress session and restore the scheduled status."""
    _ensure_in_progress(session)
    scheduled_workout = session.scheduled_workout
    session.delete()
    if scheduled_workout is not None:
        scheduling.recompute_status_after_session_change(
            scheduled_workout,
            today or timezone.localdate(),
            has_completed_session=False,
        )
