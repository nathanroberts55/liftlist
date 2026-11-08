from datetime import date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from apps.exercises.models import Exercise
from apps.stats.services import aggregations
from apps.workouts.models import Session, Tag

from .factories import add_exercise, make_session

TODAY = date(2026, 11, 9)


def _quads_exercise(muscles):
    return Exercise.objects.create(
        user=None,
        name="Leg Extension",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )


def test_range_start_translates_keys():
    assert aggregations.range_start("3m", TODAY) == date(2026, 8, 9)
    assert aggregations.range_start("6m", TODAY) == date(2026, 5, 9)
    assert aggregations.range_start("1y", TODAY) == date(2025, 11, 9)
    assert aggregations.range_start("all", TODAY) is None
    assert aggregations.range_start("nonsense", TODAY) == date(2026, 8, 9)


@pytest.mark.django_db
def test_top_set_series_uses_the_best_set_per_date(user, seeded_exercise):
    morning = make_session(user, day=date(2026, 11, 2))
    add_exercise(
        morning,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 5},
            {"weight_lb": "90", "reps": 8},
        ],
    )
    evening = make_session(user, day=date(2026, 11, 2))
    add_exercise(evening, seeded_exercise, [{"weight_lb": "110", "reps": 3}])
    latest = make_session(user, day=TODAY)
    add_exercise(latest, seeded_exercise, [{"weight_lb": "105", "reps": 6}])

    points = aggregations.top_set_series(user, seeded_exercise)

    assert [point["weight"] for point in points] == [110.0, 105.0]
    assert points[0]["date"] == "2026-11-02"
    assert points[0]["reps"] == 3
    assert [row["weight_label"] for row in points[0]["sets"]] == ["100", "90", "110"]


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_top_set_chart_filters_by_range_and_builds_tooltips(user, seeded_exercise):
    old = make_session(user, day=date(2026, 8, 1))
    add_exercise(old, seeded_exercise, [{"weight_lb": "95", "reps": 5}])
    recent = make_session(user, day=date(2026, 9, 1))
    add_exercise(recent, seeded_exercise, [{"weight_lb": "100", "reps": 5}])
    latest = make_session(user, day=TODAY)
    add_exercise(latest, seeded_exercise, [{"weight_lb": "105", "reps": 6}])

    three_months = aggregations.top_set_chart(user, seeded_exercise, "3m", TODAY)
    everything = aggregations.top_set_chart(user, seeded_exercise, "all", TODAY)

    assert three_months["labels"] == ["Sep 1", "Nov 9"]
    assert three_months["values"] == [100.0, 105.0]
    assert three_months["tooltips"] == ["100 lb × 5", "105 lb × 6"]
    assert three_months["range"] == "3m"
    assert everything["labels"] == ["Aug 1", "Sep 1", "Nov 9"]


@pytest.mark.django_db
def test_top_set_series_ignores_other_users_and_non_weighted_exercises(user, other_user, muscles):
    cardio = Exercise.objects.create(
        user=None,
        name="Row",
        primary_muscle=muscles["Cardio"],
        tracking_type=Exercise.TrackingType.CARDIO,
    )
    other = make_session(other_user, day=TODAY)
    add_exercise(other, cardio, [{"duration_seconds": 600}])
    session = make_session(user, day=TODAY)
    add_exercise(session, cardio, [{"duration_seconds": 600}])

    assert aggregations.top_set_series(other_user, cardio) == []
    assert aggregations.top_set_series(user, cardio) == []


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_weekly_volume_groups_sets_by_iso_week_and_primary_muscle(user, muscles, seeded_exercise):
    quads = _quads_exercise(muscles)
    first_week = make_session(user, day=date(2026, 9, 21))
    add_exercise(first_week, seeded_exercise, [{"weight_lb": "100", "reps": 10}])
    last_week = make_session(user, day=TODAY)
    add_exercise(
        last_week,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 10},
            {"weight_lb": "100", "reps": 10},
        ],
        order=0,
    )
    add_exercise(last_week, quads, [{"weight_lb": "120", "reps": 5}], order=1)

    chart = aggregations.weekly_volume(user, weeks=8, metric="sets", today=TODAY)

    assert len(chart["labels"]) == 8
    assert chart["weeks"][0] == "2026-09-21"
    assert chart["weeks"][-1] == "2026-11-09"
    assert [series["name"] for series in chart["series"]] == ["Chest", "Quads"]
    chest = chart["series"][0]
    assert chest["values"][0] == 1
    assert chest["values"][-1] == 2
    assert chest["total"] == 3
    assert chart["series"][1]["values"][-1] == 1
    assert chart["max"] == 3


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_weekly_volume_tonnage_only_counts_weight_reps(user, muscles, seeded_exercise):
    quads = _quads_exercise(muscles)
    session = make_session(user, day=TODAY)
    add_exercise(
        session,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 10},
            {"weight_lb": "100", "reps": 10, "status": "SKIPPED"},
        ],
        order=0,
    )
    add_exercise(session, quads, [{"weight_lb": "120", "reps": 5}], order=1)

    chart = aggregations.weekly_volume(user, metric="tonnage", today=TODAY)

    assert chart["unit"] == "lb"
    assert chart["series"][0]["name"] == "Chest"
    assert chart["series"][0]["total"] == 1000.0
    assert chart["series"][0]["total_label"] == "1,000"
    assert chart["series"][1]["total"] == 600.0
    assert chart["max"] == 1000.0


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_weekly_volume_can_include_or_exclude_a_tag(user, seeded_exercise):
    pt = Tag.objects.create(user=user, name="PT")
    tagged = make_session(user, day=TODAY)
    tagged.tags.add(pt)
    add_exercise(tagged, seeded_exercise, [{"weight_lb": "100", "reps": 10}])
    untagged = make_session(user, day=date(2026, 11, 2))
    add_exercise(untagged, seeded_exercise, [{"weight_lb": "100", "reps": 10}])

    excluded = aggregations.weekly_volume(user, tag_exclude=pt, today=TODAY)
    included = aggregations.weekly_volume(user, tag_include=pt, today=TODAY)

    assert excluded["series"][0]["total"] == 1
    assert included["series"][0]["total"] == 1


@pytest.mark.django_db
def test_record_table_searches_filters_and_is_user_scoped(
    user, other_user, muscles, seeded_exercise
):
    quads = _quads_exercise(muscles)
    session = make_session(user, day=TODAY)
    add_exercise(
        session,
        seeded_exercise,
        [{"weight_lb": "100", "reps": 10}],
        order=0,
    )
    add_exercise(session, quads, [{"weight_lb": "120", "reps": 5}], order=1)
    secret = Exercise.objects.create(
        user=other_user,
        name="Secret Lift",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    other_session = make_session(other_user, day=TODAY)
    add_exercise(other_session, secret, [{"weight_lb": "500", "reps": 1}])

    all_rows = aggregations.record_table(user)
    searched = aggregations.record_table(user, query="bench")
    by_muscle = aggregations.record_table(user, muscle_slug="quads")

    assert [row["exercise"].name for row in all_rows] == [
        "Barbell Bench Press",
        "Leg Extension",
    ]
    assert [row["exercise"].name for row in searched] == ["Barbell Bench Press"]
    assert [row["exercise"].name for row in by_muscle] == ["Leg Extension"]
    assert all(row["records"].heaviest.weight_lb != Decimal("500") for row in all_rows)


@pytest.mark.django_db
def test_recent_sessions_returns_the_last_five_newest_first(user, seeded_exercise):
    for offset in range(6):
        session = make_session(user, day=date(2026, 10, offset + 1))
        add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 5}])

    recent = aggregations.recent_sessions(user, seeded_exercise)

    assert len(recent) == 5
    assert [item.session.performed_date for item in recent] == [
        date(2026, 10, 6),
        date(2026, 10, 5),
        date(2026, 10, 4),
        date(2026, 10, 3),
        date(2026, 10, 2),
    ]


@pytest.mark.django_db
def test_exercise_with_history_prefers_a_valid_choice_and_falls_back(
    user, other_user, muscles, seeded_exercise
):
    quads = _quads_exercise(muscles)
    old = make_session(user, day=date(2026, 11, 2))
    add_exercise(old, seeded_exercise, [{"weight_lb": "100", "reps": 5}])
    latest = make_session(user, day=TODAY)
    add_exercise(latest, quads, [{"weight_lb": "120", "reps": 5}])
    secret = Exercise.objects.create(
        user=other_user,
        name="Secret Lift",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )

    assert aggregations.exercise_with_history(user, preferred_id=seeded_exercise.pk) == (
        seeded_exercise
    )
    assert aggregations.exercise_with_history(user, preferred_id=secret.pk) == quads
    assert aggregations.exercise_with_history(user) == quads
    assert aggregations.exercise_with_history(other_user, preferred_id=secret.pk) is None


@pytest.mark.django_db
def test_weighted_exercises_only_lists_trained_weighted_exercises(user, muscles, seeded_exercise):
    untrained = _quads_exercise(muscles)
    session = make_session(user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 5}])

    names = list(aggregations.weighted_exercises(user).values_list("name", flat=True))

    assert names == ["Barbell Bench Press"]
    assert untrained.name not in names


@pytest.mark.django_db
def test_tag_lookup_is_scoped_to_the_user(user, other_user):
    mine = Tag.objects.create(user=user, name="PT")
    theirs = Tag.objects.create(user=other_user, name="Theirs")

    assert aggregations.tag_lookup(user, str(mine.pk)) == mine
    assert aggregations.tag_lookup(user, str(theirs.pk)) is None
    assert aggregations.tag_lookup(user, "not-a-number") is None
    assert aggregations.tag_lookup(user, None) is None


@pytest.mark.django_db
def test_top_set_series_uses_distance_for_weight_distance_exercises(user, muscles):
    sled = Exercise.objects.create(
        user=None,
        name="Sled Push",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_DISTANCE,
    )
    session = make_session(user, day=TODAY)
    add_exercise(session, sled, [{"weight_lb": "180", "distance_mi": "0.5"}])

    chart = aggregations.top_set_chart(user, sled, "all", TODAY)

    assert chart["values"] == [180.0]
    assert chart["tooltips"] == ["180 lb × 0.5 mi"]


@pytest.mark.django_db
def test_completed_logs_excludes_in_progress_sessions(user, seeded_exercise):
    session = make_session(
        user,
        day=TODAY,
        status=Session.Status.IN_PROGRESS,
        completed_at=None,
    )
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 5}])

    assert aggregations.top_set_series(user, seeded_exercise) == []
