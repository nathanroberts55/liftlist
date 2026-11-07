"""Unscheduled sessions, retro logs, and history editing (F-06, F-09)."""

from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.plans.services import scheduling

from ..models import Session, SessionExercise, SetLog
from . import runner
from . import tags as tag_services


def _clean_title(title) -> str:
    cleaned = (title or "").strip()
    if not cleaned:
        raise ValidationError("Enter a workout title.")
    if len(cleaned) > 100:
        raise ValidationError("Keep the title to 100 characters or fewer.")
    return cleaned


def _target_kwargs(item) -> dict:
    return {
        "target_sets": item["target_sets"],
        "planned_sets": item["target_sets"],
        "rep_min": item.get("rep_min"),
        "rep_max": item.get("rep_max"),
        "target_seconds": item.get("target_seconds"),
        "target_distance_mi": item.get("target_distance_mi"),
        "rest_seconds": item.get("rest_seconds", 90),
    }


def _create_exercises(session: Session, items) -> None:
    SessionExercise.objects.bulk_create(
        [
            SessionExercise(
                session=session,
                exercise=item["exercise"],
                order=index,
                **_target_kwargs(item),
            )
            for index, item in enumerate(items)
        ]
    )


@transaction.atomic
def start_unscheduled_session(user, *, title, tag_ids=(), items) -> Session:
    """Create an in-progress unscheduled session and snapshot its exercises."""
    if not items:
        raise ValidationError("Add at least one exercise.")
    if Session.objects.filter(user=user, status=Session.Status.IN_PROGRESS).exists():
        raise ValidationError("Finish or discard your current workout first.")
    tags = tag_services.resolve_tags(user, tag_ids)
    now = timezone.now()
    session = Session.objects.create(
        user=user,
        kind=Session.Kind.UNSCHEDULED,
        title=_clean_title(title),
        performed_date=timezone.localdate(),
        status=Session.Status.IN_PROGRESS,
        started_at=now,
    )
    session.tags.set(tags)
    _create_exercises(session, items)
    return session


@transaction.atomic
def create_retro_session(
    user,
    *,
    title,
    performed_date,
    start_time=None,
    duration_seconds=None,
    tag_ids=(),
    items,
) -> Session:
    """Create a completed session that happened in the past."""
    if not items:
        raise ValidationError("Add at least one exercise.")
    if performed_date > timezone.localdate():
        raise ValidationError("Pick today or a past date.")
    tags = tag_services.resolve_tags(user, tag_ids)
    started_at = None
    completed_at = None
    if start_time is not None:
        started_at = timezone.make_aware(datetime.combine(performed_date, start_time))
        completed_at = (
            started_at + timedelta(seconds=duration_seconds)
            if duration_seconds is not None
            else started_at
        )
    session = Session.objects.create(
        user=user,
        kind=Session.Kind.UNSCHEDULED,
        title=_clean_title(title),
        performed_date=performed_date,
        status=Session.Status.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration_seconds,
        is_retro_log=True,
    )
    session.tags.set(tags)
    _create_exercises(session, items)
    return session


@transaction.atomic
def update_session_metadata(user, session: Session, *, title, performed_date, tag_ids=()):
    """Change a session's title, performed date, and tags."""
    if session.user_id != user.pk:
        raise ValidationError("That workout does not belong to you.")
    if performed_date > timezone.localdate():
        raise ValidationError("Pick today or a past date.")
    session.title = _clean_title(title)
    session.performed_date = performed_date
    session.save(update_fields=["title", "performed_date", "updated_at"])
    session.tags.set(tag_services.resolve_tags(user, tag_ids))
    if session.scheduled_workout_id and session.is_completed:
        scheduling.recompute_status_after_session_change(
            session.scheduled_workout,
            timezone.localdate(),
            has_completed_session=True,
            performed_date=performed_date,
        )
    return session


@transaction.atomic
def delete_session(user, session: Session, *, today=None) -> None:
    """Delete a completed session and restore its Scheduled Workout status."""
    if session.user_id != user.pk:
        raise ValidationError("That workout does not belong to you.")
    if session.is_in_progress:
        raise ValidationError("Discard an in-progress workout from the runner instead.")
    scheduled_workout = session.scheduled_workout
    session.delete()
    if scheduled_workout is not None:
        scheduling.recompute_status_after_session_change(
            scheduled_workout,
            today or timezone.localdate(),
            has_completed_session=False,
        )


# --- Set editing ------------------------------------------------------------


def _assert_editable(user, session: Session, session_exercise: SessionExercise) -> None:
    if session.user_id != user.pk:
        raise ValidationError("That workout does not belong to you.")
    if session_exercise.session_id != session.pk:
        raise ValidationError("That exercise is not part of this workout.")
    if not session.is_completed:
        raise ValidationError("Finish the workout before editing its sets.")


@transaction.atomic
def add_manual_set(user, session: Session, session_exercise: SessionExercise, data) -> SetLog:
    """Add a set to a completed session from the history detail screen."""
    _assert_editable(user, session, session_exercise)
    values = runner.validate_set_fields(session_exercise.exercise.tracking_type, data)
    set_number = session_exercise.next_set_number
    log = SetLog.objects.create(
        session_exercise=session_exercise,
        set_number=set_number,
        status=SetLog.Status.DONE,
        is_extra=set_number > session_exercise.planned_sets,
        completed_at=timezone.now(),
        **values,
    )
    runner.refresh_status(session_exercise)
    return log


@transaction.atomic
def update_manual_set(user, set_log: SetLog, data) -> SetLog:
    """Edit any set on a completed session (including a previously skipped set)."""
    session_exercise = set_log.session_exercise
    session = session_exercise.session
    _assert_editable(user, session, session_exercise)
    values = runner.validate_set_fields(session_exercise.exercise.tracking_type, data)
    set_log.status = SetLog.Status.DONE
    for field, value in values.items():
        setattr(set_log, field, value)
    set_log.save(
        update_fields=[
            "status",
            "weight_lb",
            "reps",
            "duration_seconds",
            "distance_mi",
            "difficulty",
        ]
    )
    runner.refresh_status(session_exercise)
    return set_log


@transaction.atomic
def delete_manual_set(user, set_log: SetLog) -> None:
    """Delete a set and keep the remaining set numbers contiguous."""
    session_exercise = set_log.session_exercise
    _assert_editable(user, session_exercise.session, session_exercise)
    removed_number = set_log.set_number
    set_log.delete()
    for remaining in session_exercise.sets.filter(set_number__gt=removed_number).order_by(
        "set_number"
    ):
        remaining.set_number -= 1
        remaining.is_extra = remaining.set_number > session_exercise.planned_sets
        remaining.save(update_fields=["set_number", "is_extra"])
    runner.refresh_status(session_exercise)
