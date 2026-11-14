"""Workout models: tags, sessions, the runner snapshot, and logged sets."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.exercises.models import DistanceUnit


class Tag(models.Model):
    """A user-defined session tag (F-06 stores and filters by these later)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workout_tags",
    )
    name = models.CharField(max_length=30)
    color = models.CharField(max_length=7, default="#2b7fff")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "user",
                name="unique_user_tag_name",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Session(models.Model):
    """One actual workout, linked to a Scheduled Workout or unscheduled."""

    class Kind(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        UNSCHEDULED = "UNSCHEDULED", "Unscheduled"

    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SCHEDULED)
    scheduled_workout = models.OneToOneField(
        "plans.ScheduledWorkout",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="session",
    )
    plan_day = models.ForeignKey(
        "plans.PlanDay",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sessions",
    )
    title = models.CharField(max_length=100)
    performed_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    is_retro_log = models.BooleanField(default=False)
    tags = models.ManyToManyField(Tag, blank=True, related_name="sessions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-performed_date", "-started_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="IN_PROGRESS"),
                name="one_in_progress_session_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} on {self.performed_date}"

    @property
    def is_in_progress(self) -> bool:
        return self.status == self.Status.IN_PROGRESS

    @property
    def is_completed(self) -> bool:
        return self.status == self.Status.COMPLETED

    @property
    def done_set_count(self) -> int:
        return sum(exercise.done_count for exercise in self.session_exercises.all())

    @property
    def target_set_count(self) -> int:
        return sum(exercise.target_sets for exercise in self.session_exercises.all())

    @property
    def done_exercise_count(self) -> int:
        return sum(
            1
            for exercise in self.session_exercises.all()
            if exercise.status in (SessionExercise.Status.DONE, SessionExercise.Status.SKIPPED)
        )

    @property
    def exercise_count(self) -> int:
        return len(self.session_exercises.all())

    @property
    def progress_label(self) -> str:
        return f"{self.done_set_count} of {self.target_set_count} sets"

    @property
    def elapsed_seconds(self) -> int | None:
        if self.duration_seconds is not None:
            return self.duration_seconds
        if self.started_at is None:
            return None
        end = self.completed_at or timezone.now()
        return max(0, int((end - self.started_at).total_seconds()))

    @property
    def elapsed_label(self) -> str:
        seconds = self.elapsed_seconds
        if seconds is None:
            return ""
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes}:{remainder:02d}"


class SessionExercise(models.Model):
    """A Session's snapshot of one exercise's targets."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        DONE = "DONE", "Done"
        SKIPPED = "SKIPPED", "Skipped"

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="session_exercises",
    )
    exercise = models.ForeignKey(
        "exercises.Exercise",
        on_delete=models.PROTECT,
        related_name="session_exercises",
    )
    plan_item = models.ForeignKey(
        "plans.PlanItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="session_exercises",
    )
    order = models.PositiveSmallIntegerField(default=0)
    superset_group = models.CharField(max_length=1, blank=True, default="")
    target_sets = models.PositiveSmallIntegerField(default=3)
    planned_sets = models.PositiveSmallIntegerField(default=3)
    rep_min = models.PositiveSmallIntegerField(null=True, blank=True)
    rep_max = models.PositiveSmallIntegerField(null=True, blank=True)
    target_seconds = models.PositiveIntegerField(null=True, blank=True)
    target_distance_m = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    distance_unit = models.CharField(
        max_length=2,
        choices=DistanceUnit.choices,
        default=DistanceUnit.MILES,
    )
    rest_seconds = models.PositiveSmallIntegerField(default=90)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(target_sets__gte=1),
                name="session_exercise_target_sets_positive",
            ),
            models.CheckConstraint(
                condition=Q(planned_sets__gte=1),
                name="session_exercise_planned_sets_positive",
            ),
            models.CheckConstraint(
                condition=Q(rep_min__isnull=True)
                | Q(rep_max__isnull=True)
                | Q(rep_min__lte=F("rep_max")),
                name="session_exercise_rep_range",
            ),
            models.CheckConstraint(
                condition=Q(rest_seconds__lte=3600),
                name="session_exercise_rest_within_hour",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.exercise} in {self.session}"

    @property
    def logged_count(self) -> int:
        return sum(1 for _ in self.sets.all())

    @property
    def done_count(self) -> int:
        return sum(1 for log in self.sets.all() if log.status == SetLog.Status.DONE)

    @property
    def next_set_number(self) -> int:
        numbers = [log.set_number for log in self.sets.all()]
        return max(numbers, default=0) + 1

    @property
    def is_complete(self) -> bool:
        if self.status in (self.Status.DONE, self.Status.SKIPPED):
            return True
        return self.logged_count >= self.target_sets

    @property
    def done_sets(self):
        return [log for log in self.sets.all() if log.status == SetLog.Status.DONE]

    @property
    def target_summary(self) -> str:
        """Short target label used on Today and in the runner."""
        from apps.exercises.models import Exercise
        from apps.exercises.services.units import format_distance

        tracking = self.exercise.tracking_type
        if tracking in (Exercise.TrackingType.WEIGHT_REPS, Exercise.TrackingType.BODYWEIGHT):
            if self.rep_min is None or self.rep_max is None:
                return f"{self.target_sets} sets"
            reps = (
                str(self.rep_min)
                if self.rep_min == self.rep_max
                else f"{self.rep_min}–{self.rep_max}"
            )
            return f"{self.target_sets} × {reps}"
        if tracking == Exercise.TrackingType.TIMED:
            if self.target_seconds is None:
                return f"{self.target_sets} sets"
            return f"{self.target_sets} × {_format_seconds(self.target_seconds)}"
        if tracking == Exercise.TrackingType.CARDIO:
            parts = []
            if self.target_seconds:
                parts.append(_format_seconds(self.target_seconds))
            if self.target_distance_m is not None:
                parts.append(format_distance(self.target_distance_m, self.distance_unit))
            return " · ".join(parts) or "1 set"
        if tracking == Exercise.TrackingType.DISTANCE:
            if self.target_distance_m is not None:
                distance = format_distance(self.target_distance_m, self.distance_unit)
                return f"{self.target_sets} × {distance}"
            return f"{self.target_sets} sets"
        return f"{self.target_sets} sets"

    @property
    def distance_unit_short(self) -> str:
        return DistanceUnit(self.distance_unit).short_label

    @property
    def goal_label(self) -> str:
        """The sentence shown under the set count, e.g. ``Goal 8–12 reps``."""
        from apps.exercises.models import Exercise
        from apps.exercises.services.units import format_distance

        tracking = self.exercise.tracking_type
        if tracking in (Exercise.TrackingType.WEIGHT_REPS, Exercise.TrackingType.BODYWEIGHT):
            if self.rep_min is None or self.rep_max is None:
                return f"Goal {self.target_sets} sets"
            reps = (
                str(self.rep_min)
                if self.rep_min == self.rep_max
                else f"{self.rep_min}–{self.rep_max}"
            )
            return f"Goal {reps} reps"
        if tracking == Exercise.TrackingType.TIMED:
            if self.target_seconds is None:
                return f"Goal {self.target_sets} sets"
            return f"Goal {_format_seconds(self.target_seconds)}"
        if tracking == Exercise.TrackingType.CARDIO:
            parts = []
            if self.target_seconds:
                parts.append(_format_seconds(self.target_seconds))
            if self.target_distance_m is not None:
                parts.append(format_distance(self.target_distance_m, self.distance_unit))
            return "Goal " + " · ".join(parts) if parts else "Goal 1 set"
        if tracking == Exercise.TrackingType.DISTANCE:
            if self.target_distance_m is not None:
                return f"Goal {format_distance(self.target_distance_m, self.distance_unit)}"
            return f"Goal {self.target_sets} sets"
        return f"Goal {self.target_sets} sets"


class SetLog(models.Model):
    """One recorded (or skipped) set. Immutable once the session is complete."""

    class Status(models.TextChoices):
        DONE = "DONE", "Done"
        SKIPPED = "SKIPPED", "Skipped"

    session_exercise = models.ForeignKey(
        SessionExercise,
        on_delete=models.CASCADE,
        related_name="sets",
    )
    set_number = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DONE)
    weight_lb = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    reps = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    distance_m = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    difficulty = models.PositiveSmallIntegerField(null=True, blank=True)
    is_extra = models.BooleanField(default=False)
    client_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    completed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["set_number", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["session_exercise", "set_number"],
                name="unique_set_number_per_exercise",
            ),
            models.CheckConstraint(
                condition=Q(difficulty__isnull=True)
                | (Q(difficulty__gte=1) & Q(difficulty__lte=10)),
                name="set_log_difficulty_range",
            ),
        ]

    def __str__(self) -> str:
        return f"Set {self.set_number} of {self.session_exercise}"

    @property
    def display_value(self) -> str:
        from apps.exercises.models import Exercise
        from apps.exercises.services.units import format_distance

        tracking = self.session_exercise.exercise.tracking_type
        unit = self.session_exercise.distance_unit
        if tracking == Exercise.TrackingType.WEIGHT_REPS:
            weight = _trim_decimal(self.weight_lb) if self.weight_lb is not None else "—"
            return f"{weight} × {self.reps or 0}"
        if tracking == Exercise.TrackingType.BODYWEIGHT:
            if self.weight_lb is not None and self.weight_lb > 0:
                return f"{self.reps or 0} (+{_trim_decimal(self.weight_lb)} lb)"
            return f"{self.reps or 0} reps"
        if tracking == Exercise.TrackingType.TIMED:
            value = _format_seconds(self.duration_seconds) if self.duration_seconds else "—"
            if self.weight_lb is not None and self.weight_lb > 0:
                return f"{value} (+{_trim_decimal(self.weight_lb)} lb)"
            return value
        if tracking == Exercise.TrackingType.CARDIO:
            parts = []
            if self.duration_seconds is not None:
                parts.append(_format_seconds(self.duration_seconds))
            if self.distance_m is not None:
                parts.append(format_distance(self.distance_m, unit))
            return " · ".join(parts) or "—"
        if tracking == Exercise.TrackingType.DISTANCE:
            weight = _trim_decimal(self.weight_lb) if self.weight_lb is not None else None
            reps = f"{self.reps} steps" if self.reps is not None else None
            distance = (
                format_distance(self.distance_m, unit) if self.distance_m is not None else None
            )
            values = [value for value in (weight and f"{weight} lb", reps, distance) if value]
            return " · ".join(values) or "—"
        return "—"


def _format_seconds(seconds: int) -> str:
    minutes, remainder = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}:{remainder:02d}"
    return f"{remainder}s"


def _trim_decimal(value) -> str:
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"
