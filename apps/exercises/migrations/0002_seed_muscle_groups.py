"""Seed the fixed muscle groups (PRD F-02 §8.1)."""

from django.db import migrations

MUSCLE_GROUPS = [
    ("Chest", "chest"),
    ("Back", "back"),
    ("Shoulders", "shoulders"),
    ("Biceps", "biceps"),
    ("Triceps", "triceps"),
    ("Forearms", "forearms"),
    ("Quads", "quads"),
    ("Hamstrings", "hamstrings"),
    ("Glutes", "glutes"),
    ("Calves", "calves"),
    ("Core", "core"),
    ("Cardio", "cardio"),
]


def seed_muscle_groups(apps, schema_editor):
    MuscleGroup = apps.get_model("exercises", "MuscleGroup")
    for order, (name, slug) in enumerate(MUSCLE_GROUPS, start=1):
        MuscleGroup.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "display_order": order},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("exercises", "0001_initial"),
    ]

    operations = [
        # Reversing would have to delete rows that exercises may already point at,
        # so it is a no-op by design.
        migrations.RunPython(seed_muscle_groups, migrations.RunPython.noop),
    ]
