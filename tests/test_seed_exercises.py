import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.exercises.models import Exercise, ExerciseArchive, MuscleGroup

REAL_SEED_COUNT = 96


@pytest.mark.django_db
def test_seed_creates_the_full_library():
    call_command("seed_exercises", stdout=StringIO())

    assert MuscleGroup.objects.count() == 12
    assert Exercise.objects.filter(user__isnull=True).count() == REAL_SEED_COUNT
    bench = Exercise.objects.get(name="Barbell Bench Press")
    assert bench.primary_muscle.name == "Chest"
    assert bench.tracking_type == Exercise.TrackingType.WEIGHT_REPS
    assert {muscle.name for muscle in bench.secondary_muscles.all()} == {
        "Shoulders",
        "Triceps",
    }


@pytest.mark.django_db
def test_seed_is_idempotent():
    call_command("seed_exercises", stdout=StringIO())
    call_command("seed_exercises", stdout=StringIO())

    assert Exercise.objects.filter(user__isnull=True).count() == REAL_SEED_COUNT


@pytest.mark.django_db
def test_seed_preserves_user_archives(user):
    call_command("seed_exercises", stdout=StringIO())
    bench = Exercise.objects.get(name="Barbell Bench Press")
    ExerciseArchive.objects.create(user=user, exercise=bench)

    call_command("seed_exercises", stdout=StringIO())

    assert ExerciseArchive.objects.filter(user=user, exercise=bench).exists()
    assert Exercise.objects.filter(user__isnull=True).count() == REAL_SEED_COUNT


@pytest.mark.django_db
def test_seed_repairs_drifted_seeded_rows(muscles):
    call_command("seed_exercises", stdout=StringIO())
    bench = Exercise.objects.get(name="Barbell Bench Press")
    bench.primary_muscle = muscles["Back"]
    bench.tracking_type = Exercise.TrackingType.CARDIO
    bench.save(update_fields=["primary_muscle", "tracking_type"])

    call_command("seed_exercises", stdout=StringIO())

    bench.refresh_from_db()
    assert bench.primary_muscle == muscles["Chest"]
    assert bench.tracking_type == Exercise.TrackingType.WEIGHT_REPS


@pytest.mark.django_db
def test_seed_repairs_a_case_only_name_drift():
    call_command("seed_exercises", stdout=StringIO())
    bench = Exercise.objects.get(name="Barbell Bench Press")
    Exercise.objects.filter(pk=bench.pk).update(name="barbell bench press")

    call_command("seed_exercises", stdout=StringIO())

    bench.refresh_from_db()
    assert bench.name == "Barbell Bench Press"
    assert Exercise.objects.filter(user__isnull=True).count() == REAL_SEED_COUNT


@pytest.mark.django_db
def test_seed_does_not_touch_custom_exercises(user, muscles):
    Exercise.objects.create(
        user=user,
        name="Barbell Bench Press",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.CARDIO,
    )

    call_command("seed_exercises", stdout=StringIO())

    custom = Exercise.objects.get(user=user)
    assert custom.primary_muscle == muscles["Back"]
    global_row = Exercise.objects.get(user=None, name="Barbell Bench Press")
    assert global_row.primary_muscle == muscles["Chest"]


def write_seed_file(tmp_path, payload):
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "exercises.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


@pytest.mark.django_db
def test_seed_rejects_an_unknown_muscle(tmp_path, settings, muscles):
    settings.BASE_DIR = write_seed_file(
        tmp_path,
        [
            {
                "name": "Mystery Move",
                "primary": "Neck",
                "secondary": [],
                "tracking_type": "WEIGHT_REPS",
            }
        ],
    )

    with pytest.raises(CommandError, match="unknown primary muscle"):
        call_command("seed_exercises", stdout=StringIO())


@pytest.mark.django_db
def test_seed_rejects_an_unknown_tracking_type(tmp_path, settings, muscles):
    settings.BASE_DIR = write_seed_file(
        tmp_path,
        [
            {
                "name": "Mystery Move",
                "primary": "Chest",
                "secondary": [],
                "tracking_type": "VIBES",
            }
        ],
    )

    with pytest.raises(CommandError, match="unknown tracking type"):
        call_command("seed_exercises", stdout=StringIO())


@pytest.mark.django_db
def test_seed_rejects_duplicate_names_in_the_file(tmp_path, settings, muscles):
    settings.BASE_DIR = write_seed_file(
        tmp_path,
        [
            {
                "name": "Same Move",
                "primary": "Chest",
                "secondary": [],
                "tracking_type": "WEIGHT_REPS",
            },
            {
                "name": "same move",
                "primary": "Back",
                "secondary": [],
                "tracking_type": "WEIGHT_REPS",
            },
        ],
    )

    with pytest.raises(CommandError, match="Duplicate exercise name"):
        call_command("seed_exercises", stdout=StringIO())


@pytest.mark.django_db
def test_seed_rejects_a_missing_file(tmp_path, settings, muscles):
    settings.BASE_DIR = tmp_path

    with pytest.raises(CommandError, match="Seed file not found"):
        call_command("seed_exercises", stdout=StringIO())
