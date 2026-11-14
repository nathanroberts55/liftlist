"""Plan builder and scheduling models (F-03, F-04)."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.exercises.models import DistanceUnit


class Weekday(models.IntegerChoices):
    """Python ``date.weekday()`` values, so no conversion is needed."""

    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


WEEKDAY_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class PlanQuerySet(models.QuerySet):
    def for_user(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(user=user)

    def active_for(self, user):
        return self.for_user(user).filter(status=Plan.Status.ACTIVE)


class Plan(models.Model):
    """A training block. One plan per user can be active at a time."""

    class SplitType(models.TextChoices):
        FULL_BODY = "FULL_BODY", "Full Body"
        UPPER_LOWER = "UPPER_LOWER", "Upper/Lower"
        PPL = "PPL", "Push/Pull/Legs"
        BODY_PART = "BODY_PART", "Body-Part Split"
        CUSTOM = "CUSTOM", "Custom"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="plans",
    )
    name = models.CharField(max_length=100)
    split_type = models.CharField(
        max_length=20,
        choices=SplitType.choices,
        default=SplitType.CUSTOM,
    )
    start_date = models.DateField()
    length_weeks = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Leave blank for an open-ended plan.",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PlanQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="ACTIVE"),
                name="one_active_plan_per_user",
            ),
            models.CheckConstraint(
                condition=Q(length_weeks__isnull=True) | Q(length_weeks__gte=1),
                name="plan_length_weeks_positive",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_draft(self) -> bool:
        return self.status == self.Status.DRAFT

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def is_archived(self) -> bool:
        return self.status == self.Status.ARCHIVED


class PlanDay(models.Model):
    """One weekday in a plan, with its ordered exercises."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="days")
    name = models.CharField(max_length=60)
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    order = models.PositiveSmallIntegerField(default=0)
    focus_muscles = models.ManyToManyField(
        "exercises.MuscleGroup",
        blank=True,
        related_name="plan_days",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["weekday", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "weekday"],
                name="one_plan_day_per_weekday",
            ),
            models.CheckConstraint(
                condition=Q(weekday__gte=0) & Q(weekday__lte=6),
                name="plan_day_weekday_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_weekday_display()})"

    @property
    def weekday_short(self) -> str:
        return WEEKDAY_SHORT[self.weekday]


class PlanItem(models.Model):
    """An exercise placed in a Plan Day, with targets and rest."""

    plan_day = models.ForeignKey(PlanDay, on_delete=models.CASCADE, related_name="items")
    exercise = models.ForeignKey(
        "exercises.Exercise",
        on_delete=models.PROTECT,
        related_name="plan_items",
    )
    order = models.PositiveSmallIntegerField(default=0)
    superset_group = models.CharField(
        max_length=1,
        blank=True,
        default="",
        help_text="A–Z when this item belongs to a superset; blank otherwise.",
    )
    target_sets = models.PositiveSmallIntegerField(default=3)
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
    notes = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.CheckConstraint(
                condition=Q(rep_min__isnull=True)
                | Q(rep_max__isnull=True)
                | Q(rep_min__lte=F("rep_max")),
                name="plan_item_rep_range",
            ),
            models.CheckConstraint(
                condition=Q(target_sets__gte=1),
                name="plan_item_target_sets_positive",
            ),
            models.CheckConstraint(
                condition=Q(rest_seconds__lte=3600),
                name="plan_item_rest_within_hour",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.exercise} in {self.plan_day}"

    @property
    def tracking_type(self) -> str:
        return self.exercise.tracking_type

    @property
    def target_summary(self) -> str:
        """Short target label used on Today, the plan list, and the runner."""
        from apps.exercises.models import Exercise

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
                from apps.exercises.services.units import format_distance

                parts.append(format_distance(self.target_distance_m, self.distance_unit))
            return " · ".join(parts) or "1 set"
        if tracking == Exercise.TrackingType.DISTANCE:
            if self.target_distance_m is not None:
                from apps.exercises.services.units import format_distance

                distance = format_distance(self.target_distance_m, self.distance_unit)
                return f"{self.target_sets} × {distance}"
            return f"{self.target_sets} sets"
        return f"{self.target_sets} sets"

    @property
    def distance_unit_short(self) -> str:
        return DistanceUnit(self.distance_unit).short_label

    @property
    def rest_label(self) -> str:
        return f"{self.rest_seconds}s"


def _format_seconds(seconds: int) -> str:
    minutes, remainder = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}:{remainder:02d}"
    return f"{remainder}s"


class ScheduledWorkoutQuerySet(models.QuerySet):
    def for_user(self, user):
        if not user.is_authenticated:
            return self.none()
        return self.filter(user=user)

    def upcoming(self):
        return self.exclude(status=ScheduledWorkout.Status.COMPLETED)


class ScheduledWorkout(models.Model):
    """A Plan Day placed on a calendar date by the scheduler."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        MISSED = "MISSED", "Missed"
        MADE_UP = "MADE_UP", "Made up"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scheduled_workouts",
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
        related_name="scheduled_workouts",
    )
    plan_day = models.ForeignKey(
        PlanDay,
        on_delete=models.CASCADE,
        related_name="scheduled_workouts",
    )
    scheduled_date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    marked_missed_manually = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ScheduledWorkoutQuerySet.as_manager()

    class Meta:
        ordering = ["scheduled_date", "plan_day__weekday"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "plan_day", "scheduled_date"],
                name="unique_scheduled_workout",
            )
        ]
        indexes = [models.Index(fields=["user", "scheduled_date"], name="sched_user_date_idx")]

    def __str__(self) -> str:
        return f"{self.plan_day} on {self.scheduled_date}"
