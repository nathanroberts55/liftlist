from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models

METERS_PER_MILE = Decimal("1609.344")
METERS_QUANTUM = Decimal("0.0001")
MILES_QUANTUM = Decimal("0.01")


def _convert(model, field, operation):
    for row in model.objects.exclude(**{f"{field}__isnull": True}).iterator():
        value = getattr(row, field)
        converted = operation(value)
        setattr(row, field, converted)
        row.save(update_fields=[field])


def forwards(apps, schema_editor):
    """Existing mile targets and logs become canonical metres (F-13)."""
    to_meters = lambda value: (value * METERS_PER_MILE).quantize(  # noqa: E731
        METERS_QUANTUM, rounding=ROUND_HALF_UP
    )
    SessionExercise = apps.get_model("workouts", "SessionExercise")
    SetLog = apps.get_model("workouts", "SetLog")
    _convert(SessionExercise, "target_distance_m", to_meters)
    _convert(SetLog, "distance_m", to_meters)


def backwards(apps, schema_editor):
    to_miles = lambda value: (value / METERS_PER_MILE).quantize(  # noqa: E731
        MILES_QUANTUM, rounding=ROUND_HALF_UP
    )
    SessionExercise = apps.get_model("workouts", "SessionExercise")
    SetLog = apps.get_model("workouts", "SetLog")
    _convert(SessionExercise, "target_distance_m", to_miles)
    _convert(SetLog, "distance_m", to_miles)


class Migration(migrations.Migration):
    dependencies = [
        ("exercises", "0003_distance_unit"),
        ("workouts", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="sessionexercise",
            old_name="target_distance_mi",
            new_name="target_distance_m",
        ),
        migrations.RenameField(
            model_name="setlog",
            old_name="distance_mi",
            new_name="distance_m",
        ),
        migrations.AlterField(
            model_name="sessionexercise",
            name="target_distance_m",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="setlog",
            name="distance_m",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="sessionexercise",
            name="distance_unit",
            field=models.CharField(
                choices=[("MI", "Miles"), ("YD", "Yards"), ("M", "Meters")],
                default="MI",
                max_length=2,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
