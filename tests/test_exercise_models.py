import pytest
from django.db import IntegrityError, transaction

from apps.exercises.models import Exercise, ExerciseArchive, MuscleGroup


@pytest.mark.django_db
def test_exercise_is_seeded_when_it_has_no_user(seeded_exercise):
    assert seeded_exercise.is_seeded is True
    assert seeded_exercise.is_custom is False


@pytest.mark.django_db
def test_exercise_is_custom_when_it_has_a_user(custom_exercise):
    assert custom_exercise.is_seeded is False
    assert custom_exercise.is_custom is True


@pytest.mark.django_db
def test_muscle_groups_are_seeded_in_prd_order(muscles):
    assert list(MuscleGroup.objects.values_list("name", flat=True)) == [
        "Chest",
        "Back",
        "Shoulders",
        "Biceps",
        "Triceps",
        "Forearms",
        "Quads",
        "Hamstrings",
        "Glutes",
        "Calves",
        "Core",
        "Cardio",
    ]


@pytest.mark.django_db
def test_visible_to_includes_seeded_and_own_custom(user, other_user, seeded_exercise):
    own = Exercise.objects.create(
        user=user,
        name="Cable Fly",
        primary_muscle=seeded_exercise.primary_muscle,
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    Exercise.objects.create(
        user=other_user,
        name="Someone Else's Move",
        primary_muscle=seeded_exercise.primary_muscle,
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )

    visible = Exercise.objects.visible_to(user)

    assert set(visible) == {seeded_exercise, own}


@pytest.mark.django_db
def test_visible_to_hides_seeded_exercises_archived_by_the_user(user, seeded_exercise):
    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)

    assert seeded_exercise not in Exercise.objects.visible_to(user)
    assert seeded_exercise in Exercise.objects.archived_for(user)


@pytest.mark.django_db
def test_visible_to_hides_archived_custom_exercises(user, custom_exercise):
    custom_exercise.is_archived = True
    custom_exercise.save(update_fields=["is_archived"])

    assert custom_exercise not in Exercise.objects.visible_to(user)
    assert custom_exercise in Exercise.objects.archived_for(user)


@pytest.mark.django_db
def test_visible_to_returns_nothing_for_anonymous_users(seeded_exercise):
    from django.contrib.auth.models import AnonymousUser

    assert list(Exercise.objects.visible_to(AnonymousUser())) == []


@pytest.mark.django_db
def test_seeded_names_are_unique_case_insensitively(seeded_exercise):
    with pytest.raises(IntegrityError), transaction.atomic():
        Exercise.objects.create(
            user=None,
            name="barbell bench press",
            primary_muscle=seeded_exercise.primary_muscle,
            tracking_type=Exercise.TrackingType.WEIGHT_REPS,
        )


@pytest.mark.django_db
def test_custom_names_are_unique_per_user(user, custom_exercise):
    with pytest.raises(IntegrityError), transaction.atomic():
        Exercise.objects.create(
            user=user,
            name="cable fly",
            primary_muscle=custom_exercise.primary_muscle,
            tracking_type=Exercise.TrackingType.WEIGHT_REPS,
        )


@pytest.mark.django_db
def test_two_users_can_use_the_same_custom_name(other_user, custom_exercise):
    duplicate = Exercise.objects.create(
        user=other_user,
        name=custom_exercise.name,
        primary_muscle=custom_exercise.primary_muscle,
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )

    assert duplicate.pk is not None


@pytest.mark.django_db
def test_archive_is_unique_per_user_and_exercise(user, seeded_exercise):
    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)

    with pytest.raises(IntegrityError), transaction.atomic():
        ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)
