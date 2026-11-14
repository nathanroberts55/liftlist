from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models

METERS_PER_MILE = Decimal("1609.344")
METERS_QUANTUM = Decimal("0.0001")
MILES_QUANTUM = Decimal("0.01")


def forwards(apps, schema_editor):
    """Existing mile values become canonical metres (F-13)."""
    PlanItem = apps.get_model("plans", "PlanItem")
    for item in PlanItem.objects.exclude(target_distance_m=None).iterator():
        item.target_distance_m = (item.target_distance_m * METERS_PER_MILE).quantize(
            METERS_QUANTUM, rounding=ROUND_HALF_UP
        )
        item.save(update_fields=["target_distance_m"])


def backwards(apps, schema_editor):
    PlanItem = apps.get_model("plans", "PlanItem")
    for item in PlanItem.objects.exclude(target_distance_m=None).iterator():
        item.target_distance_m = (item.target_distance_m / METERS_PER_MILE).quantize(
            MILES_QUANTUM, rounding=ROUND_HALF_UP
        )
        item.save(update_fields=["target_distance_m"])


class Migration(migrations.Migration):
    dependencies = [
        ("exercises", "0003_distance_unit"),
        ("plans", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="planitem",
            old_name="target_distance_mi",
            new_name="target_distance_m",
        ),
        migrations.AlterField(
            model_name="planitem",
            name="target_distance_m",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="planitem",
            name="distance_unit",
            field=models.CharField(
                choices=[("MI", "Miles"), ("YD", "Yards"), ("M", "Meters")],
                default="MI",
                max_length=2,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
