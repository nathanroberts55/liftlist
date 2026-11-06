import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404

from apps.exercises.models import Exercise, ExerciseArchive
from apps.exercises.services.library import (
    archive_exercise,
    count_archived,
    create_exercise,
    find_name_conflict,
    get_exercise,
    grouped_by_muscle,
    is_archived_for,
    list_exercises,
    restore_exercise,
    update_exercise,
    validate_name,
)


def make_custom(user, muscle, name="Cable Fly", **overrides):
    payload = {
        "user": user,
        "name": name,
        "primary_muscle": muscle,
        "tracking_type": Exercise.TrackingType.WEIGHT_REPS,
        **overrides,
    }
    return Exercise.objects.create(**payload)


# --- Reads ------------------------------------------------------------------


@pytest.mark.django_db
def test_list_exercises_returns_visible_rows_in_muscle_order(user, muscles):
    make_custom(user, muscles["Quads"], name="Leg Extension")
    seeded = Exercise.objects.create(
        user=None,
        name="Bench Press",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )

    results = list(list_exercises(user=user))

    assert results == [seeded, Exercise.objects.get(name="Leg Extension")]


@pytest.mark.django_db
def test_list_exercises_filters_by_name_case_insensitively(user, muscles):
    make_custom(user, muscles["Chest"], name="Incline Fly")
    make_custom(user, muscles["Quads"], name="Leg Press")

    results = list(list_exercises(user=user, query="FLY"))

    assert [exercise.name for exercise in results] == ["Incline Fly"]


@pytest.mark.django_db
def test_list_exercises_filters_by_primary_muscle(user, muscles):
    make_custom(user, muscles["Chest"], name="Incline Fly")
    make_custom(user, muscles["Quads"], name="Leg Press")

    results = list(list_exercises(user=user, muscle_slug="quads"))

    assert [exercise.name for exercise in results] == ["Leg Press"]


@pytest.mark.django_db
def test_list_exercises_can_list_archived_rows_only(user, muscles, seeded_exercise):
    archived = make_custom(user, muscles["Back"], name="Old Row")
    archived.is_archived = True
    archived.save(update_fields=["is_archived"])
    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)

    results = list(list_exercises(user=user, archived=True))

    assert set(results) == {archived, seeded_exercise}


@pytest.mark.django_db
def test_grouped_by_muscle_keeps_query_order(user, muscles):
    Exercise.objects.create(
        user=None,
        name="Back Squat",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    Exercise.objects.create(
        user=None,
        name="Bench Press",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    exercises = list(list_exercises(user=user))

    groups = grouped_by_muscle(exercises)

    assert [group["muscle"].name for group in groups] == ["Chest", "Quads"]
    assert [exercise.name for exercise in groups[1]["exercises"]] == ["Back Squat"]


@pytest.mark.django_db
def test_other_users_custom_exercise_is_not_found(user, other_user, muscles):
    theirs = make_custom(other_user, muscles["Chest"])

    with pytest.raises(Http404):
        get_exercise(user, theirs.pk)


@pytest.mark.django_db
def test_seeded_exercise_is_visible_to_every_user(user, other_user, seeded_exercise):
    assert get_exercise(user, seeded_exercise.pk) == seeded_exercise
    assert get_exercise(other_user, seeded_exercise.pk) == seeded_exercise


@pytest.mark.django_db
def test_is_archived_for_distinguishes_seeded_and_custom(user, seeded_exercise, custom_exercise):
    assert is_archived_for(user, seeded_exercise) is False
    assert is_archived_for(user, custom_exercise) is False

    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)
    custom_exercise.is_archived = True
    custom_exercise.save(update_fields=["is_archived"])

    assert is_archived_for(user, seeded_exercise) is True
    assert is_archived_for(user, custom_exercise) is True


@pytest.mark.django_db
def test_count_archived_counts_both_kinds(user, muscles, seeded_exercise):
    archived = make_custom(user, muscles["Back"], name="Old Row")
    archived.is_archived = True
    archived.save(update_fields=["is_archived"])
    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)

    assert count_archived(user) == 2


@pytest.mark.django_db
def test_find_name_conflict_sees_seeded_and_own_names_only(
    user, other_user, muscles, seeded_exercise
):
    assert find_name_conflict(user, "barbell bench press") == seeded_exercise
    assert find_name_conflict(user, "nobody's move") is None

    make_custom(other_user, muscles["Back"], name="Their Move")
    assert find_name_conflict(user, "their move") is None


# --- Name validation --------------------------------------------------------


@pytest.mark.django_db
def test_validate_name_trims_and_accepts_a_new_name(user):
    assert validate_name(user, "  Cable Fly  ") == "Cable Fly"


@pytest.mark.django_db
def test_validate_name_rejects_blank_names(user):
    with pytest.raises(ValidationError) as error:
        validate_name(user, "   ")

    assert error.value.code == "required"


@pytest.mark.django_db
def test_validate_name_rejects_a_visible_duplicate(user, seeded_exercise):
    with pytest.raises(ValidationError) as error:
        validate_name(user, "barbell bench press")

    assert error.value.code == "duplicate_name"
    assert "already exists" in error.value.messages[0]


@pytest.mark.django_db
def test_validate_name_points_archived_duplicates_to_restore(user, seeded_exercise):
    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)

    with pytest.raises(ValidationError) as error:
        validate_name(user, "Barbell Bench Press")

    assert error.value.code == "archived_name"
    assert "Restore it" in error.value.messages[0]


@pytest.mark.django_db
def test_validate_name_allows_the_same_name_on_another_user(
    user, other_user, muscles, seeded_exercise
):
    make_custom(other_user, muscles["Back"], name="Their Move")

    assert validate_name(user, "Their Move") == "Their Move"


@pytest.mark.django_db
def test_validate_name_allows_an_exercise_to_keep_its_own_name(user, custom_exercise):
    assert validate_name(user, "Cable Fly", exclude=custom_exercise) == "Cable Fly"


# --- Writes -----------------------------------------------------------------


@pytest.mark.django_db
def test_create_exercise_sets_secondary_muscles_and_notes(user, muscles):
    exercise = create_exercise(
        user=user,
        name="  Incline Fly  ",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.BODYWEIGHT,
        secondary_muscles=[muscles["Shoulders"]],
        notes="  Squeeze at the top  ",
    )

    assert exercise.user == user
    assert exercise.name == "Incline Fly"
    assert exercise.notes == "Squeeze at the top"
    assert list(exercise.secondary_muscles.all()) == [muscles["Shoulders"]]


@pytest.mark.django_db
def test_create_exercise_rejects_a_duplicate_name(user, muscles, seeded_exercise):
    with pytest.raises(ValidationError):
        create_exercise(
            user=user,
            name=seeded_exercise.name,
            primary_muscle=muscles["Chest"],
            tracking_type=Exercise.TrackingType.WEIGHT_REPS,
        )

    assert Exercise.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_update_exercise_changes_fields_and_secondaries(user, muscles, custom_exercise):
    updated = update_exercise(
        user=user,
        exercise=custom_exercise,
        name="Low Cable Fly",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.CARDIO,
        secondary_muscles=[muscles["Biceps"], muscles["Triceps"]],
        notes="New cue",
    )

    assert updated.name == "Low Cable Fly"
    assert updated.primary_muscle == muscles["Back"]
    assert updated.tracking_type == Exercise.TrackingType.CARDIO
    assert updated.notes == "New cue"
    assert set(updated.secondary_muscles.all()) == {muscles["Biceps"], muscles["Triceps"]}


@pytest.mark.django_db
def test_update_exercise_never_touches_a_seeded_row(user, seeded_exercise, muscles):
    with pytest.raises(PermissionDenied):
        update_exercise(
            user=user,
            exercise=seeded_exercise,
            name="Renamed",
            primary_muscle=muscles["Back"],
            tracking_type=Exercise.TrackingType.BODYWEIGHT,
        )

    seeded_exercise.refresh_from_db()
    assert seeded_exercise.name == "Barbell Bench Press"


@pytest.mark.django_db
def test_update_exercise_rejects_another_users_custom_row(user, other_user, muscles):
    theirs = make_custom(other_user, muscles["Chest"])

    with pytest.raises(PermissionDenied):
        update_exercise(
            user=user,
            exercise=theirs,
            name="Hijacked",
            primary_muscle=muscles["Back"],
            tracking_type=Exercise.TrackingType.BODYWEIGHT,
        )


@pytest.mark.django_db
def test_archiving_a_seeded_exercise_only_writes_an_archive_row(user, seeded_exercise):
    archive_exercise(user=user, exercise=seeded_exercise)

    assert ExerciseArchive.objects.filter(user=user, exercise=seeded_exercise).exists()
    seeded_exercise.refresh_from_db()
    assert seeded_exercise.user is None
    assert seeded_exercise.is_archived is False


@pytest.mark.django_db
def test_archiving_is_idempotent(user, seeded_exercise):
    archive_exercise(user=user, exercise=seeded_exercise)
    archive_exercise(user=user, exercise=seeded_exercise)

    assert ExerciseArchive.objects.filter(user=user, exercise=seeded_exercise).count() == 1


@pytest.mark.django_db
def test_archiving_a_custom_exercise_flags_it(user, custom_exercise):
    archive_exercise(user=user, exercise=custom_exercise)

    custom_exercise.refresh_from_db()
    assert custom_exercise.is_archived is True


@pytest.mark.django_db
def test_archiving_another_users_exercise_is_denied(user, other_user, muscles):
    theirs = make_custom(other_user, muscles["Chest"])

    with pytest.raises(PermissionDenied):
        archive_exercise(user=user, exercise=theirs)


@pytest.mark.django_db
def test_restoring_a_seeded_exercise_removes_the_archive(user, seeded_exercise):
    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)

    restore_exercise(user=user, exercise=seeded_exercise)

    assert not ExerciseArchive.objects.filter(user=user, exercise=seeded_exercise).exists()


@pytest.mark.django_db
def test_restoring_a_custom_exercise_clears_the_flag(user, custom_exercise):
    custom_exercise.is_archived = True
    custom_exercise.save(update_fields=["is_archived"])

    restore_exercise(user=user, exercise=custom_exercise)

    custom_exercise.refresh_from_db()
    assert custom_exercise.is_archived is False


@pytest.mark.django_db
def test_restoring_another_users_exercise_is_denied(user, other_user, muscles):
    theirs = make_custom(other_user, muscles["Chest"], is_archived=True)

    with pytest.raises(PermissionDenied):
        restore_exercise(user=user, exercise=theirs)
