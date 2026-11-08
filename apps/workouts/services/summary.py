"""Workout summary calculations (F-08).

The summary is derived on demand from the session snapshot and the user's
history. Nothing here mutates data, so editing a past session immediately
changes its summary and the stats pages that share these helpers.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.exercises.models import Exercise
from apps.plans.models import Plan, ScheduledWorkout

from ..models import Session, SessionExercise, SetLog
from . import progression, records


@dataclass(frozen=True)
class MuscleRow:
    """Sets completed for one primary muscle group."""

    name: str
    slug: str
    sets: int
    share: int
    bar_percent: int
    color_index: int


@dataclass(frozen=True)
class VolumeComparison:
    """This session's tonnage against the previous comparable session."""

    prior_volume: Decimal
    delta_percent: float | None
    direction: str
    prior_date: date | None

    @property
    def delta_label(self) -> str:
        if self.delta_percent is None:
            return ""
        rounded = round(self.delta_percent, 1)
        sign = "+" if rounded > 0 else ""
        return f"{sign}{rounded:g}%"

    @property
    def prior_volume_label(self) -> str:
        return format_volume(self.prior_volume)


@dataclass(frozen=True)
class Adherence:
    """Active-plan adherence counts plus the current streak."""

    plan_name: str
    completed: int
    made_up: int
    missed: int
    streak: int

    @property
    def has_history(self) -> bool:
        return bool(self.completed or self.made_up or self.missed)


@dataclass(frozen=True)
class Summary:
    """Every PRD F-08 field, ready for the template."""

    session: Session
    duration_seconds: int | None
    duration_label: str
    done_sets: int
    planned_sets: int
    extra_sets: int
    skipped_sets: int
    volume: Decimal
    volume_label: str
    comparison: VolumeComparison | None
    prs: list
    increase_exercises: list[SessionExercise]
    muscles: list[MuscleRow]
    avg_difficulty: float | None
    adherence: Adherence | None

    @property
    def sets_label(self) -> str:
        label = f"{self.done_sets} of {self.planned_sets}"
        if self.extra_sets:
            label += f" · +{self.extra_sets} extra"
        if self.skipped_sets:
            label += f" · {self.skipped_sets} skipped"
        return label


# --- Helpers ----------------------------------------------------------------


def _trim_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".") or "0"


def format_volume(value: Decimal) -> str:
    """Group the whole-number part with commas and keep meaningful decimals."""
    text = _trim_decimal(value)
    whole, dot, fraction = text.partition(".")
    grouped = f"{int(whole):,}"
    return f"{grouped}.{fraction}" if dot else grouped


def session_volume(session: Session) -> Decimal:
    """Tonnage: DONE ``WEIGHT_REPS`` sets only (weight × reps)."""
    logs = SetLog.objects.filter(
        session_exercise__session=session,
        session_exercise__exercise__tracking_type=Exercise.TrackingType.WEIGHT_REPS,
        status=SetLog.Status.DONE,
        weight_lb__isnull=False,
        reps__isnull=False,
    ).values_list("weight_lb", "reps")
    return sum((weight * reps for weight, reps in logs), Decimal("0"))


def _comparison_session(session: Session) -> Session | None:
    """The previous completed session of the same Plan Day, or same title."""
    queryset = Session.objects.filter(
        user=session.user,
        status=Session.Status.COMPLETED,
    ).exclude(pk=session.pk)
    if session.kind == Session.Kind.SCHEDULED and session.plan_day_id:
        queryset = queryset.filter(plan_day_id=session.plan_day_id)
    else:
        queryset = queryset.filter(title=session.title)
    prior = queryset.order_by("-performed_date", "-completed_at", "-pk")
    for candidate in prior:
        if records.session_is_earlier(candidate, session):
            return candidate
    return None


def _comparison(session: Session, volume: Decimal) -> VolumeComparison | None:
    prior = _comparison_session(session)
    if prior is None:
        return None
    prior_volume = session_volume(prior)
    if prior_volume == 0:
        return VolumeComparison(
            prior_volume=prior_volume,
            delta_percent=None,
            direction="flat",
            prior_date=prior.performed_date,
        )
    delta = float((volume - prior_volume) / prior_volume * 100)
    if delta > 0:
        direction = "up"
    elif delta < 0:
        direction = "down"
    else:
        direction = "flat"
    return VolumeComparison(
        prior_volume=prior_volume,
        delta_percent=delta,
        direction=direction,
        prior_date=prior.performed_date,
    )


def adherence(plan: Plan | None, today: date | None = None) -> Adherence | None:
    """Counts by status for a plan, plus the current streak (PRD F-08)."""
    if plan is None:
        return None
    today = today or timezone.localdate()
    workouts = plan.scheduled_workouts.exclude(status=ScheduledWorkout.Status.PENDING)
    counts = {"COMPLETED": 0, "MADE_UP": 0, "MISSED": 0}
    for status in workouts.values_list("status", flat=True):
        if status in counts:
            counts[status] += 1

    streak = 0
    past = (
        plan.scheduled_workouts.filter(scheduled_date__lte=today)
        .exclude(status=ScheduledWorkout.Status.PENDING)
        .order_by("-scheduled_date", "-pk")
        .values_list("status", flat=True)
    )
    for status in past:
        if status == ScheduledWorkout.Status.MISSED:
            break
        if status in (ScheduledWorkout.Status.COMPLETED, ScheduledWorkout.Status.MADE_UP):
            streak += 1
    return Adherence(
        plan_name=plan.name,
        completed=counts["COMPLETED"],
        made_up=counts["MADE_UP"],
        missed=counts["MISSED"],
        streak=streak,
    )


def _muscle_rows(exercises: list[SessionExercise]) -> list[MuscleRow]:
    counts: dict[int, dict] = {}
    for session_exercise in exercises:
        muscle = session_exercise.exercise.primary_muscle
        done = sum(1 for log in session_exercise.sets.all() if log.status == SetLog.Status.DONE)
        if not done:
            continue
        entry = counts.setdefault(
            muscle.pk,
            {
                "name": muscle.name,
                "slug": muscle.slug,
                "order": muscle.display_order,
                "sets": 0,
            },
        )
        entry["sets"] += done
    if not counts:
        return []
    total = sum(entry["sets"] for entry in counts.values())
    max_sets = max(entry["sets"] for entry in counts.values())
    rows = [
        MuscleRow(
            name=entry["name"],
            slug=entry["slug"],
            sets=entry["sets"],
            share=round(entry["sets"] / total * 100),
            bar_percent=max(4, round(entry["sets"] / max_sets * 100)),
            color_index=entry["order"] % 8 + 1,
        )
        for entry in counts.values()
    ]
    return sorted(rows, key=lambda row: (-row.sets, row.name))


def _average_difficulty(exercises: list[SessionExercise]) -> float | None:
    values = [
        log.difficulty
        for session_exercise in exercises
        for log in session_exercise.sets.all()
        if log.status == SetLog.Status.DONE and log.difficulty is not None
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 1)


# --- Public API -------------------------------------------------------------


def build_summary(session: Session, today: date | None = None) -> Summary:
    """Build every PRD F-08 field for a completed (or in-progress) session."""
    exercises = list(
        session.session_exercises.select_related(
            "exercise",
            "exercise__primary_muscle",
        ).prefetch_related("sets")
    )
    logs = [log for exercise in exercises for log in exercise.sets.all()]

    done_sets = sum(1 for log in logs if log.status == SetLog.Status.DONE)
    skipped_sets = sum(1 for log in logs if log.status == SetLog.Status.SKIPPED)
    extra_sets = sum(1 for log in logs if log.status == SetLog.Status.DONE and log.is_extra)
    planned_sets = sum(exercise.planned_sets for exercise in exercises)

    volume = Decimal("0")
    for session_exercise in exercises:
        if session_exercise.exercise.tracking_type != Exercise.TrackingType.WEIGHT_REPS:
            continue
        for log in session_exercise.sets.all():
            if (
                log.status == SetLog.Status.DONE
                and log.weight_lb is not None
                and log.reps is not None
            ):
                volume += log.weight_lb * log.reps

    plan = None
    if session.scheduled_workout_id:
        plan = session.scheduled_workout.plan
    else:
        plan = Plan.objects.active_for(session.user).first()

    return Summary(
        session=session,
        duration_seconds=session.elapsed_seconds,
        duration_label=session.elapsed_label,
        done_sets=done_sets,
        planned_sets=planned_sets,
        extra_sets=extra_sets,
        skipped_sets=skipped_sets,
        volume=volume,
        volume_label=format_volume(volume),
        comparison=_comparison(session, volume),
        prs=records.prs_set_in_session(session),
        increase_exercises=[
            exercise for exercise in exercises if progression.increase_flag(exercise)
        ],
        muscles=_muscle_rows(exercises),
        avg_difficulty=_average_difficulty(exercises),
        adherence=adherence(plan, today),
    )
