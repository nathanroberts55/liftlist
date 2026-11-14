"""Exercise library services.

Views stay thin: parse input, call one of these functions, render. Everything
that decides *what* is visible, editable, or archived lives here.
"""

from itertools import groupby

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404

from ..models import DistanceUnit, Exercise, ExerciseArchive, MuscleGroup

# --- Reads ------------------------------------------------------------------


def list_exercises(*, user, query: str = "", muscle_slug: str = "", archived: bool = False):
    """Return the library rows for one user, optionally filtered."""
    queryset = (
        Exercise.objects.archived_for(user) if archived else Exercise.objects.visible_to(user)
    )
    queryset = queryset.select_related("primary_muscle").prefetch_related("secondary_muscles")
    if query:
        queryset = queryset.filter(name__icontains=query)
    if muscle_slug:
        queryset = queryset.filter(primary_muscle__slug=muscle_slug)
    return queryset.order_by("primary_muscle__display_order", "name")


def grouped_by_muscle(exercises) -> list[dict]:
    """Group an ordered exercise iterable into ``{muscle, exercises}`` blocks."""
    groups = []
    for muscle, items in groupby(exercises, key=lambda exercise: exercise.primary_muscle):
        groups.append({"muscle": muscle, "exercises": list(items)})
    return groups


def get_exercise(user, exercise_id) -> Exercise:
    """Fetch a seeded or user-owned exercise; 404 for anyone else's custom row."""
    return get_object_or_404(
        Exercise.objects.select_related("primary_muscle").prefetch_related("secondary_muscles"),
        Q(user=user) | Q(user__isnull=True),
        pk=exercise_id,
    )


def is_archived_for(user, exercise: Exercise) -> bool:
    """Whether this exercise is hidden for this user."""
    if exercise.is_seeded:
        return ExerciseArchive.objects.filter(user=user, exercise=exercise).exists()
    return exercise.is_archived


def count_archived(user) -> int:
    return Exercise.objects.archived_for(user).count()


def find_name_conflict(user, name: str, *, exclude: Exercise | None = None):
    """Return the seeded or user-owned exercise using ``name`` (case-insensitive)."""
    queryset = Exercise.objects.filter(
        Q(user__isnull=True) | Q(user=user),
        name__iexact=name.strip(),
    )
    if exclude is not None and exclude.pk is not None:
        queryset = queryset.exclude(pk=exclude.pk)
    return queryset.first()


def validate_name(user, name: str, *, exclude: Exercise | None = None) -> str:
    """Normalize a name and reject duplicates with a message the user can act on."""
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Enter an exercise name.", code="required")
    conflict = find_name_conflict(user, cleaned, exclude=exclude)
    if conflict is not None:
        if is_archived_for(user, conflict):
            raise ValidationError(
                f"An archived exercise already uses the name “{cleaned}”. Restore it instead.",
                code="archived_name",
            )
        raise ValidationError(
            f"An exercise named “{cleaned}” already exists.",
            code="duplicate_name",
        )
    return cleaned


# --- Writes -----------------------------------------------------------------


@transaction.atomic
def create_exercise(
    *,
    user,
    name: str,
    primary_muscle: MuscleGroup,
    tracking_type: str,
    default_distance_unit: str = DistanceUnit.MILES,
    secondary_muscles=(),
    notes: str = "",
) -> Exercise:
    """Create a custom exercise for ``user``."""
    name = validate_name(user, name)
    exercise = Exercise(
        user=user,
        name=name,
        primary_muscle=primary_muscle,
        tracking_type=tracking_type,
        default_distance_unit=default_distance_unit,
        notes=notes.strip(),
    )
    exercise.clean_fields()
    try:
        exercise.save()
    except IntegrityError as error:
        raise ValidationError(
            f"An exercise named “{name}” already exists.", code="duplicate_name"
        ) from error
    exercise.secondary_muscles.set(secondary_muscles)
    return exercise


@transaction.atomic
def update_exercise(
    *,
    user,
    exercise: Exercise,
    name: str,
    primary_muscle: MuscleGroup,
    tracking_type: str,
    default_distance_unit: str = DistanceUnit.MILES,
    secondary_muscles=(),
    notes: str = "",
) -> Exercise:
    """Edit a custom exercise. Seeded rows are immutable."""
    if exercise.is_seeded:
        raise PermissionDenied("Seeded exercises can't be edited.")
    if exercise.user_id != user.id:
        raise PermissionDenied("You can only edit your own exercises.")

    name = validate_name(user, name, exclude=exercise)
    exercise.name = name
    exercise.primary_muscle = primary_muscle
    exercise.tracking_type = tracking_type
    exercise.default_distance_unit = default_distance_unit
    exercise.notes = notes.strip()
    exercise.clean_fields()
    try:
        exercise.save()
    except IntegrityError as error:
        raise ValidationError(
            f"An exercise named “{name}” already exists.", code="duplicate_name"
        ) from error
    exercise.secondary_muscles.set(secondary_muscles)
    return exercise


def archive_exercise(*, user, exercise: Exercise) -> None:
    """Hide an exercise for this user without deleting anything."""
    if exercise.is_seeded:
        ExerciseArchive.objects.get_or_create(user=user, exercise=exercise)
        return
    if exercise.user_id != user.id:
        raise PermissionDenied("You can only archive your own exercises.")
    exercise.is_archived = True
    exercise.save(update_fields=["is_archived", "updated_at"])


def restore_exercise(*, user, exercise: Exercise) -> None:
    """Undo a previous archive for this user."""
    if exercise.is_seeded:
        ExerciseArchive.objects.filter(user=user, exercise=exercise).delete()
        return
    if exercise.user_id != user.id:
        raise PermissionDenied("You can only restore your own exercises.")
    exercise.is_archived = False
    exercise.save(update_fields=["is_archived", "updated_at"])
