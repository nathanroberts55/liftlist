"""Progression services: last time, pre-fill, and the increase flag (F-07)."""

from apps.exercises.models import Exercise
from apps.exercises.services.units import format_distance

from ..models import Session, SessionExercise, SetLog


def last_time(
    user,
    exercise,
    plan_day=None,
    *,
    exclude_session=None,
) -> SessionExercise | None:
    """The most recent completed SessionExercise, preferring the same Plan Day."""
    queryset = (
        SessionExercise.objects.filter(
            session__user=user,
            session__status=Session.Status.COMPLETED,
            exercise=exercise,
        )
        .select_related("session")
        .prefetch_related("sets")
        .order_by(
            "-session__performed_date",
            "-session__completed_at",
            "-session__pk",
            "-pk",
        )
    )
    if exclude_session is not None:
        queryset = queryset.exclude(session=exclude_session)
    if plan_day is not None:
        preferred = queryset.filter(session__plan_day=plan_day).first()
        if preferred is not None:
            return preferred
    return queryset.first()


def _done_logs(session_exercise: SessionExercise) -> list[SetLog]:
    return [log for log in session_exercise.sets.all() if log.status == SetLog.Status.DONE]


def _same_set(logs: list[SetLog], set_number: int) -> SetLog | None:
    return next((log for log in logs if log.set_number == set_number), None)


def prefill(user, session_exercise: SessionExercise, set_number: int) -> dict:
    """Values for the next set, following PRD F-07."""
    last = last_time(
        user,
        session_exercise.exercise,
        session_exercise.session.plan_day,
        exclude_session=session_exercise.session,
    )
    values = {
        "weight_lb": None,
        "reps": session_exercise.rep_max,
        "duration_seconds": session_exercise.target_seconds,
        "distance_m": session_exercise.target_distance_m,
    }
    if last is None:
        return values

    logs = sorted(_done_logs(last), key=lambda log: log.set_number)
    if not logs:
        return values

    same = _same_set(logs, set_number)
    final = logs[-1]
    values["weight_lb"] = (
        same.weight_lb if same is not None and same.weight_lb is not None else final.weight_lb
    )
    if same is not None:
        if same.reps is not None:
            values["reps"] = same.reps
        if same.duration_seconds is not None:
            values["duration_seconds"] = same.duration_seconds
        if same.distance_m is not None:
            values["distance_m"] = same.distance_m
    return values


def increase_flag(session_exercise: SessionExercise) -> bool:
    """Whether the exercise earned a "ready to increase" flag."""
    if session_exercise.exercise.tracking_type not in (
        Exercise.TrackingType.WEIGHT_REPS,
        Exercise.TrackingType.BODYWEIGHT,
    ):
        return False
    if session_exercise.rep_max is None:
        return False
    logs = [log for log in _done_logs(session_exercise) if not log.is_extra]
    if len(logs) < session_exercise.planned_sets:
        return False
    return all(log.reps is not None and log.reps >= session_exercise.rep_max for log in logs)


def flag_for_upcoming(user, exercise, plan_day=None) -> bool:
    last = last_time(user, exercise, plan_day)
    return increase_flag(last) if last is not None else False


def last_time_display(user, session_exercise: SessionExercise) -> str:
    """A compact "Last:" value such as ``225×8, 225×8, 225×7``."""
    last = last_time(
        user,
        session_exercise.exercise,
        session_exercise.session.plan_day,
        exclude_session=session_exercise.session,
    )
    if last is None:
        return ""
    logs = sorted(_done_logs(last), key=lambda log: log.set_number)
    if not logs:
        return ""
    tracking = session_exercise.exercise.tracking_type
    if tracking in (Exercise.TrackingType.WEIGHT_REPS, Exercise.TrackingType.BODYWEIGHT):
        parts = []
        for log in logs:
            if log.weight_lb is not None and log.weight_lb > 0:
                parts.append(f"{_trim(log.weight_lb)}×{log.reps or 0}")
            else:
                parts.append(f"{log.reps or 0}")
        return ", ".join(parts)
    if tracking == Exercise.TrackingType.TIMED:
        return ", ".join(_seconds(log.duration_seconds) for log in logs)
    if tracking == Exercise.TrackingType.CARDIO:
        return " · ".join(_cardio(log, last.distance_unit) for log in logs)
    if tracking == Exercise.TrackingType.DISTANCE:
        parts = []
        for log in logs:
            values = []
            if log.weight_lb is not None:
                values.append(f"{_trim(log.weight_lb)} lb")
            if log.reps is not None:
                values.append(f"{log.reps} steps")
            if log.distance_m is not None:
                values.append(format_distance(log.distance_m, last.distance_unit))
            parts.append(" · ".join(values) or "—")
        return ", ".join(parts)
    return ""


def _trim(value) -> str:
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"


def _seconds(seconds) -> str:
    if seconds is None:
        return "—"
    minutes, remainder = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}:{remainder:02d}"
    return f"{remainder}s"


def _cardio(log: SetLog, distance_unit) -> str:
    parts = []
    if log.duration_seconds is not None:
        parts.append(_seconds(log.duration_seconds))
    if log.distance_m is not None:
        parts.append(format_distance(log.distance_m, distance_unit))
    return " · ".join(parts) or "—"
