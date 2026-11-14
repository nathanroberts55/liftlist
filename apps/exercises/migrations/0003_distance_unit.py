from django.db import migrations, models

YARD_DEFAULT_EXERCISES = ("Sled Push", "Sled Pull", "Farmer's Carry")


def forwards(apps, schema_editor):
    """Rename the old tracking type and give the sled/carry seeds yards."""
    Exercise = apps.get_model("exercises", "Exercise")
    Exercise.objects.filter(tracking_type="WEIGHT_DISTANCE").update(tracking_type="DISTANCE")
    Exercise.objects.filter(
        user__isnull=True,
        name__in=YARD_DEFAULT_EXERCISES,
    ).update(default_distance_unit="YD")


def backwards(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")
    Exercise.objects.filter(tracking_type="DISTANCE").update(tracking_type="WEIGHT_DISTANCE")


class Migration(migrations.Migration):
    dependencies = [
        ("exercises", "0002_seed_muscle_groups"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exercise",
            name="tracking_type",
            field=models.CharField(
                choices=[
                    ("WEIGHT_REPS", "Weight × Reps"),
                    ("BODYWEIGHT", "Bodyweight"),
                    ("TIMED", "Timed"),
                    ("CARDIO", "Cardio"),
                    ("DISTANCE", "Distance"),
                ],
                default="WEIGHT_REPS",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="exercise",
            name="default_distance_unit",
            field=models.CharField(
                choices=[("MI", "Miles"), ("YD", "Yards"), ("M", "Meters")],
                default="MI",
                help_text="Used for CARDIO and DISTANCE exercises unless an item overrides it.",
                max_length=2,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
