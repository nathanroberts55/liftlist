"""Seed the global exercise library from ``seed/exercises.json`` (F-02)."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.exercises.models import DistanceUnit, Exercise, MuscleGroup


class Command(BaseCommand):
    help = "Create or update the seeded exercise library. Safe to run repeatedly."

    def handle(self, *args, **options):
        path = Path(settings.BASE_DIR) / "seed" / "exercises.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise CommandError(f"Seed file not found: {path}") from error
        except json.JSONDecodeError as error:
            raise CommandError(f"Seed file is not valid JSON: {path}") from error

        if not isinstance(payload, list):
            raise CommandError("Seed file must contain a list of exercises.")

        muscles = {muscle.name: muscle for muscle in MuscleGroup.objects.all()}
        if not muscles:
            raise CommandError("Muscle groups are missing. Run `python manage.py migrate` first.")

        created = updated = unchanged = 0
        seen_names = set()
        with transaction.atomic():
            for index, row in enumerate(payload):
                self._validate_row(row, index, muscles)
                name = row["name"].strip()
                if name.lower() in seen_names:
                    raise CommandError(f"Duplicate exercise name in seed file: {name}")
                seen_names.add(name.lower())

                primary = muscles[row["primary"]]
                secondary = [muscles[muscle] for muscle in row.get("secondary", [])]
                unit = row.get("default_distance_unit", DistanceUnit.MILES)
                exercise = Exercise.objects.filter(user=None, name__iexact=name).first()
                if exercise is None:
                    exercise = Exercise.objects.create(
                        user=None,
                        name=name,
                        primary_muscle=primary,
                        tracking_type=row["tracking_type"],
                        default_distance_unit=unit,
                    )
                    exercise.secondary_muscles.set(secondary)
                    created += 1
                    continue

                current_secondary = set(exercise.secondary_muscles.values_list("pk", flat=True))
                if (
                    exercise.name != name
                    or exercise.primary_muscle_id != primary.pk
                    or exercise.tracking_type != row["tracking_type"]
                    or exercise.default_distance_unit != unit
                    or current_secondary != {muscle.pk for muscle in secondary}
                ):
                    exercise.name = name
                    exercise.primary_muscle = primary
                    exercise.tracking_type = row["tracking_type"]
                    exercise.default_distance_unit = unit
                    exercise.save(
                        update_fields=[
                            "name",
                            "primary_muscle",
                            "tracking_type",
                            "default_distance_unit",
                            "updated_at",
                        ]
                    )
                    exercise.secondary_muscles.set(secondary)
                    updated += 1
                else:
                    unchanged += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Exercises seeded: {created} created, {updated} updated, {unchanged} unchanged."
            )
        )

    def _validate_row(self, row, index, muscles) -> None:
        where = f"Seed row {index + 1}"
        if not isinstance(row, dict):
            raise CommandError(f"{where}: expected an object.")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CommandError(f"{where}: name is required.")
        primary = row.get("primary")
        if primary not in muscles:
            raise CommandError(f"{where} ({name}): unknown primary muscle {primary!r}.")
        tracking_type = row.get("tracking_type")
        if tracking_type not in Exercise.TrackingType.values:
            raise CommandError(f"{where} ({name}): unknown tracking type {tracking_type!r}.")
        unit = row.get("default_distance_unit", DistanceUnit.MILES)
        if unit not in DistanceUnit.values:
            raise CommandError(f"{where} ({name}): unknown default distance unit {unit!r}.")
        if unit != DistanceUnit.MILES and tracking_type not in (
            Exercise.TrackingType.CARDIO,
            Exercise.TrackingType.DISTANCE,
        ):
            raise CommandError(
                f"{where} ({name}): a distance unit only applies to CARDIO or DISTANCE."
            )
        secondary = row.get("secondary", [])
        if not isinstance(secondary, list) or any(muscle not in muscles for muscle in secondary):
            raise CommandError(f"{where} ({name}): unknown secondary muscle.")
