"""Exercise library models: muscle groups, exercises, and per-user archives."""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class MuscleGroup(models.Model):
    """A fixed, seeded muscle group. Read-only in the UI."""

    name = models.CharField(max_length=40, unique=True)
    slug = models.SlugField(max_length=40, unique=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name


class ExerciseQuerySet(models.QuerySet):
    """Query helpers that keep global rows and user archives separate."""

    def visible_to(self, user):
        """Seeded exercises the user has not archived, plus their custom ones."""
        if not user.is_authenticated:
            return self.none()
        archived_ids = ExerciseArchive.objects.filter(user=user).values("exercise_id")
        return self.filter(
            (Q(user__isnull=True) & ~Q(pk__in=archived_ids)) | Q(user=user, is_archived=False)
        )

    def archived_for(self, user):
        """Exercises the user has hidden, whether seeded or custom."""
        if not user.is_authenticated:
            return self.none()
        archived_ids = ExerciseArchive.objects.filter(user=user).values("exercise_id")
        return self.filter(Q(pk__in=archived_ids) | Q(user=user, is_archived=True))


class Exercise(models.Model):
    """A movement the user can put in a plan or log sets for.

    Seeded exercises have ``user = NULL``; custom exercises belong to one user.
    Seeded rows are never mutated by a user's archive action (see
    :class:`ExerciseArchive`), so one user's choice cannot affect another's.
    """

    class TrackingType(models.TextChoices):
        WEIGHT_REPS = "WEIGHT_REPS", "Weight × Reps"
        BODYWEIGHT = "BODYWEIGHT", "Bodyweight"
        TIMED = "TIMED", "Timed"
        CARDIO = "CARDIO", "Cardio"
        WEIGHT_DISTANCE = "WEIGHT_DISTANCE", "Weight × Distance"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="exercises",
    )
    name = models.CharField(max_length=100)
    primary_muscle = models.ForeignKey(
        MuscleGroup,
        on_delete=models.PROTECT,
        related_name="primary_exercises",
    )
    secondary_muscles = models.ManyToManyField(
        MuscleGroup,
        blank=True,
        related_name="secondary_exercises",
    )
    tracking_type = models.CharField(
        max_length=20,
        choices=TrackingType.choices,
        default=TrackingType.WEIGHT_REPS,
    )
    notes = models.TextField(blank=True)
    is_archived = models.BooleanField(
        default=False,
        help_text="Custom exercises only. Seeded exercises use ExerciseArchive.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ExerciseQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                condition=Q(user__isnull=True),
                name="unique_seeded_exercise_name",
            ),
            models.UniqueConstraint(
                Lower("name"),
                "user",
                condition=Q(user__isnull=False),
                name="unique_user_exercise_name",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_seeded(self) -> bool:
        return self.user_id is None

    @property
    def is_custom(self) -> bool:
        return self.user_id is not None


class ExerciseArchive(models.Model):
    """A per-user archive of a seeded exercise (global rows stay untouched)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exercise_archives",
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name="user_archives",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "exercise"],
                name="unique_exercise_archive_per_user",
            )
        ]

    def __str__(self) -> str:
        return f"{self.exercise} archived by {self.user}"
