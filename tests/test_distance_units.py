"""Distance unit conversions and formatting (F-13)."""

from decimal import Decimal

from apps.exercises.models import DistanceUnit
from apps.exercises.services import units


def test_miles_round_trip_without_losing_precision():
    meters = units.to_meters("2.48", "MI")

    assert meters == Decimal("3991.1731")
    assert units.format_distance(meters, "MI") == "2.48 mi"


def test_yards_and_metres_round_trip():
    yards = units.to_meters("15", "YD")
    metres = units.to_meters("400", "M")

    assert yards == Decimal("13.7160")
    assert units.format_distance(yards, "YD") == "15 yd"
    assert metres == Decimal("400.0000")
    assert units.format_distance(metres, "M") == "400 m"


def test_display_value_is_trimmed_for_inputs():
    assert units.display_value(Decimal("13.7160"), "YD") == "15"
    assert units.display_value(Decimal("4988.9664"), "MI") == "3.1"
    assert units.display_value(None, "MI") == ""


def test_blank_and_unknown_units_fall_back_to_miles():
    assert units.normalize_unit("") == DistanceUnit.MILES
    assert units.normalize_unit(None) == DistanceUnit.MILES
    assert units.normalize_unit("FEET") == DistanceUnit.MILES
    assert units.normalize_unit("YD") == DistanceUnit.YARDS


def test_to_meters_ignores_blank_and_invalid_values():
    assert units.to_meters("", "MI") is None
    assert units.to_meters(None, "MI") is None
    assert units.to_meters("soon", "MI") is None
