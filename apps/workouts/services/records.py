"""Personal-record calculations (F-10).

PRs are computed from the current data on demand; they are never stored. The
rules live here so the summary, exercise detail page, and stats page all agree.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.exercises.models import Exercise

from ..models import Session, SetLog

WEIGHT_TRACKING_TYPES = (
    Exercise.TrackingType.WEIGHT_REPS,
    Exercise.TrackingType.DISTANCE,
)


@dataclass(frozen=True)
class RecordSet:
    """One set that owns a record, with enough context to display it."""

    weight_lb: Decimal | None
    reps: int | None
    performed_date: date
    session_id: int
    set_number: int
    is_extra: bool = False


@dataclass(frozen=True)
class PR:
    """A PR hit in one session. ``kind`` is ``heaviest`` or ``reps``."""

    kind: str
    exercise: Exercise
    weight_lb: Decimal | None
    reps: int | None
    performed_date: date
    session_id: int
    set_number: int

    @property
    def label(self) -> str:
        weight = _trim(self.weight_lb)
        if self.kind == "heaviest":
            return f"{weight} lb (new heaviest)"
        return f"{self.reps or 0} reps @ {weight} lb"


@dataclass(frozen=True)
class ExerciseRecords:
    exercise: Exercise
    heaviest: RecordSet | None
    reps_by_weight: list[RecordSet]


def session_is_earlier(candidate: Session, current: Session) -> bool:
    """Whether ``candidate`` sorts before ``current`` by performed date/time.

    ``completed_at`` can be null for retro logs, so equal dates fall back to the
    primary key, which is still deterministic and matches the displayed order.
    """
    if candidate.performed_date != current.performed_date:
        return candidate.performed_date < current.performed_date
    if current.completed_at is None:
        return candidate.pk < current.pk
    if candidate.completed_at is None:
        return True
    return candidate.completed_at < current.completed_at


def _trim(value: Decimal | None) -> str:
    if value is None:
        return "—"
    text = format(value, "f")
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".") or "0"


def _weighted_sets(user, exercise):
    """DONE sets with a weight for weight-based exercises."""
    if exercise.tracking_type not in WEIGHT_TRACKING_TYPES:
        return SetLog.objects.none()
    queryset = SetLog.objects.filter(
        session_exercise__session__user=user,
        session_exercise__session__status=Session.Status.COMPLETED,
        session_exercise__exercise=exercise,
        status=SetLog.Status.DONE,
        weight_lb__isnull=False,
    )
    if exercise.tracking_type == Exercise.TrackingType.WEIGHT_REPS:
        queryset = queryset.filter(reps__gte=1)
    return queryset


def _record(log: SetLog) -> RecordSet:
    return RecordSet(
        weight_lb=log.weight_lb,
        reps=log.reps,
        performed_date=log.session_exercise.session.performed_date,
        session_id=log.session_exercise.session_id,
        set_number=log.set_number,
        is_extra=log.is_extra,
    )


def prs_for_exercise(user, exercise) -> ExerciseRecords:
    """Heaviest weight and the best reps at each exact weight for one exercise."""
    logs = list(
        _weighted_sets(user, exercise)
        .select_related("session_exercise__session")
        .order_by(
            "session_exercise__session__performed_date",
            "session_exercise__session__completed_at",
            "session_exercise__session__pk",
            "pk",
        )
    )
    if not logs:
        return ExerciseRecords(exercise=exercise, heaviest=None, reps_by_weight=[])

    heaviest_log = max(
        logs,
        key=lambda log: (
            log.weight_lb,
            log.reps or 0,
            log.session_exercise.session.performed_date,
            log.pk,
        ),
    )

    by_weight: dict[Decimal, RecordSet] = {}
    for log in logs:
        current = by_weight.get(log.weight_lb)
        if current is None:
            by_weight[log.weight_lb] = _record(log)
            continue
        current_key = (current.reps or 0, current.performed_date, current.session_id)
        candidate_key = (
            log.reps or 0,
            log.session_exercise.session.performed_date,
            log.session_exercise.session_id,
        )
        if candidate_key >= current_key:
            by_weight[log.weight_lb] = _record(log)

    reps_by_weight = sorted(
        by_weight.values(),
        key=lambda record: (-record.weight_lb, -(record.reps or 0)),
    )
    return ExerciseRecords(
        exercise=exercise,
        heaviest=_record(heaviest_log),
        reps_by_weight=reps_by_weight,
    )


def _previous_logs_by_exercise(session: Session, exercise_ids) -> dict[int, list[SetLog]]:
    """DONE weighted sets from sessions that sort before ``session``."""
    logs = (
        SetLog.objects.filter(
            session_exercise__session__user=session.user,
            session_exercise__session__status=Session.Status.COMPLETED,
            session_exercise__exercise_id__in=exercise_ids,
            status=SetLog.Status.DONE,
            weight_lb__isnull=False,
        )
        .exclude(session_exercise__session=session)
        .select_related("session_exercise__exercise", "session_exercise__session")
    )
    grouped: dict[int, list[SetLog]] = {}
    for log in logs:
        if session_is_earlier(log.session_exercise.session, session):
            grouped.setdefault(log.session_exercise.exercise_id, []).append(log)
    return grouped


def _best_set(logs, *, key):
    return max(logs, key=key) if logs else None


def prs_set_in_session(session: Session) -> list[PR]:
    """New PRs earned by this session according to PRD F-10.

    A heaviest-weight PR is a set heavier than every earlier set for the
    exercise. A rep PR requires the exact weight to have been used before and
    beats every earlier rep count at that weight; the first use of a weight is
    therefore never a rep PR.
    """
    exercises = list(session.session_exercises.select_related("exercise").prefetch_related("sets"))
    previous = _previous_logs_by_exercise(session, [exercise.exercise_id for exercise in exercises])
    prs: list[PR] = []

    for session_exercise in exercises:
        exercise = session_exercise.exercise
        if exercise.tracking_type not in WEIGHT_TRACKING_TYPES:
            continue
        current_sets = [
            log
            for log in session_exercise.sets.all()
            if log.status == SetLog.Status.DONE and log.weight_lb is not None
        ]
        if exercise.tracking_type == Exercise.TrackingType.WEIGHT_REPS:
            current_sets = [log for log in current_sets if (log.reps or 0) >= 1]
        if not current_sets:
            continue

        earlier = previous.get(exercise.pk, [])
        valid_earlier = [
            log
            for log in earlier
            if exercise.tracking_type != Exercise.TrackingType.WEIGHT_REPS or (log.reps or 0) >= 1
        ]

        earlier_weights = [log.weight_lb for log in valid_earlier]
        earlier_max = max(earlier_weights) if earlier_weights else None
        best_current = _best_set(
            current_sets,
            key=lambda log: (log.weight_lb, log.reps or 0, log.set_number),
        )
        if best_current is not None and (
            earlier_max is None or best_current.weight_lb > earlier_max
        ):
            prs.append(_pr("heaviest", exercise, best_current))

        earlier_reps: dict[Decimal, int] = {}
        for log in valid_earlier:
            earlier_reps[log.weight_lb] = max(
                earlier_reps.get(log.weight_lb, 0),
                log.reps or 0,
            )
        best_reps_at_weight: dict[Decimal, SetLog] = {}
        for log in current_sets:
            if log.reps is None or log.weight_lb not in earlier_reps:
                continue
            current_best = best_reps_at_weight.get(log.weight_lb)
            if current_best is None or (log.reps, log.set_number) > (
                current_best.reps or 0,
                current_best.set_number,
            ):
                best_reps_at_weight[log.weight_lb] = log
        for weight, log in best_reps_at_weight.items():
            if (log.reps or 0) > earlier_reps[weight]:
                prs.append(_pr("reps", exercise, log))

    return sorted(prs, key=lambda pr: (pr.exercise.name, pr.kind, -(pr.weight_lb or 0)))


def _pr(kind: str, exercise: Exercise, log: SetLog) -> PR:
    return PR(
        kind=kind,
        exercise=exercise,
        weight_lb=log.weight_lb,
        reps=log.reps,
        performed_date=log.session_exercise.session.performed_date,
        session_id=log.session_exercise.session_id,
        set_number=log.set_number,
    )
