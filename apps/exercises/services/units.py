"""Distance units and canonical metre conversions (F-13).

Distances are stored canonically in metres with four decimal places. The unit
is chosen per exercise and snapshotted onto plan items and session exercises, so
editing an exercise's default unit never rewrites history.

A mile is exactly 1609.344 m and a yard exactly 0.9144 m, so ``2.48 mi``
round-trips as ``2.48 mi`` even though the stored value is ``3991.1731 m``.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from apps.exercises.models import DistanceUnit

METERS_PER_UNIT = {
    DistanceUnit.MILES: Decimal("1609.344"),
    DistanceUnit.YARDS: Decimal("0.9144"),
    DistanceUnit.METERS: Decimal("1"),
}

METERS_QUANTUM = Decimal("0.0001")


def normalize_unit(unit) -> DistanceUnit:
    """Return a valid unit, defaulting to miles for blanks or unknown values."""
    try:
        return DistanceUnit(unit)
    except ValueError:
        return DistanceUnit.MILES


def to_meters(value, unit=DistanceUnit.MILES) -> Decimal | None:
    """Convert a display-unit value to canonical metres (4 dp)."""
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    meters = amount * METERS_PER_UNIT[normalize_unit(unit)]
    return meters.quantize(METERS_QUANTUM, rounding=ROUND_HALF_UP)


def from_meters(meters, unit=DistanceUnit.MILES) -> Decimal | None:
    """Convert canonical metres to a display-unit value (4 dp)."""
    if meters is None:
        return None
    value = Decimal(meters) / METERS_PER_UNIT[normalize_unit(unit)]
    return value.quantize(METERS_QUANTUM, rounding=ROUND_HALF_UP)


def display_value(meters, unit=DistanceUnit.MILES) -> str:
    """The number to show in an input, without its unit."""
    value = from_meters(meters, unit)
    if value is None:
        return ""
    return _trim(value)


def format_distance(meters, unit=DistanceUnit.MILES) -> str:
    """A compact label such as ``2.48 mi`` or ``15 yd``."""
    value = display_value(meters, unit)
    if not value:
        return ""
    return f"{value} {normalize_unit(unit).short_label}"


def _trim(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
