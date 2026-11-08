from datetime import date, datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.exercises.models import Exercise
from apps.workouts.models import Session
from apps.workouts.services import records

from .factories import add_exercise, make_session

TODAY = date(2026, 11, 9)


@pytest.mark.django_db
def test_prs_for_exercise_returns_heaviest_and_best_reps_per_weight(user, seeded_exercise):
    first = make_session(user, day=date(2026, 11, 2))
    add_exercise(
        first,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 10},
            {"weight_lb": "110", "reps": 8},
        ],
    )
    second = make_session(user, day=TODAY)
    add_exercise(
        second,
        seeded_exercise,
        [
            {"weight_lb": "110", "reps": 9},
            {"weight_lb": "120", "reps": 6},
        ],
    )

    result = records.prs_for_exercise(user, seeded_exercise)

    assert result.heaviest.weight_lb == Decimal("120")
    assert result.heaviest.reps == 6
    assert result.heaviest.performed_date == TODAY
    assert [record.weight_lb for record in result.reps_by_weight] == [
        Decimal("120"),
        Decimal("110"),
        Decimal("100"),
    ]
    assert [record.reps for record in result.reps_by_weight] == [6, 9, 10]


@pytest.mark.django_db
def test_prs_for_exercise_is_scoped_to_the_user(user, other_user, seeded_exercise):
    other = make_session(other_user, day=date(2026, 11, 2))
    add_exercise(other, seeded_exercise, [{"weight_lb": "200", "reps": 5}])
    mine = make_session(user, day=TODAY)
    add_exercise(mine, seeded_exercise, [{"weight_lb": "100", "reps": 10}])

    result = records.prs_for_exercise(user, seeded_exercise)

    assert result.heaviest.weight_lb == Decimal("100")


@pytest.mark.django_db
def test_prs_for_exercise_has_no_records_without_completed_weighted_sets(user, seeded_exercise):
    session = make_session(user, day=TODAY)
    add_exercise(
        session,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 10, "status": "SKIPPED"},
            {"weight_lb": None, "reps": 10},
        ],
    )

    result = records.prs_for_exercise(user, seeded_exercise)

    assert result.heaviest is None
    assert result.reps_by_weight == []


@pytest.mark.django_db
def test_first_session_only_sets_a_heaviest_pr(user, seeded_exercise):
    session = make_session(user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 10}])

    prs = records.prs_set_in_session(session)

    assert [pr.kind for pr in prs] == ["heaviest"]
    assert prs[0].label == "100 lb (new heaviest)"


@pytest.mark.django_db
def test_rep_pr_requires_the_exact_weight_to_have_been_used_before(user, seeded_exercise):
    earlier = make_session(user, day=date(2026, 11, 2))
    add_exercise(earlier, seeded_exercise, [{"weight_lb": "100", "reps": 8}])
    session = make_session(user, day=TODAY)
    add_exercise(
        session,
        seeded_exercise,
        [
            {"weight_lb": "100", "reps": 9},
            {"weight_lb": "105", "reps": 5},
        ],
    )

    prs = records.prs_set_in_session(session)

    assert [pr.kind for pr in prs] == ["heaviest", "reps"]
    heaviest = next(pr for pr in prs if pr.kind == "heaviest")
    reps = next(pr for pr in prs if pr.kind == "reps")
    assert heaviest.weight_lb == Decimal("105")
    assert reps.weight_lb == Decimal("100")
    assert reps.reps == 9
    assert reps.label == "9 reps @ 100 lb"


@pytest.mark.django_db
def test_matching_or_lower_reps_do_not_set_a_pr(user, seeded_exercise):
    earlier = make_session(user, day=date(2026, 11, 2))
    add_exercise(earlier, seeded_exercise, [{"weight_lb": "100", "reps": 8}])
    session = make_session(user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 8}])

    assert records.prs_set_in_session(session) == []


@pytest.mark.django_db
def test_other_users_and_in_progress_sessions_do_not_count(user, other_user, seeded_exercise):
    other = make_session(other_user, day=date(2026, 11, 2))
    add_exercise(other, seeded_exercise, [{"weight_lb": "200", "reps": 5}])
    unfinished = make_session(
        user,
        day=date(2026, 11, 4),
        status=Session.Status.IN_PROGRESS,
        completed_at=None,
    )
    add_exercise(unfinished, seeded_exercise, [{"weight_lb": "200", "reps": 5}])
    session = make_session(user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 10}])

    prs = records.prs_set_in_session(session)

    assert [pr.kind for pr in prs] == ["heaviest"]


@pytest.mark.django_db
def test_weight_distance_records_use_weight_without_rep_prs(user, muscles):
    exercise = Exercise.objects.create(
        user=None,
        name="Sled Push",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_DISTANCE,
    )
    earlier = make_session(user, day=date(2026, 11, 2))
    add_exercise(earlier, exercise, [{"weight_lb": "100", "distance_mi": "0.5"}])
    session = make_session(user, day=TODAY)
    add_exercise(session, exercise, [{"weight_lb": "120", "distance_mi": "0.5"}])

    prs = records.prs_set_in_session(session)
    result = records.prs_for_exercise(user, exercise)

    assert [pr.kind for pr in prs] == ["heaviest"]
    assert result.heaviest.reps is None
    assert result.reps_by_weight[0].reps is None


def test_session_is_earlier_orders_by_date_then_completion_time():
    current = Session(
        performed_date=TODAY,
        completed_at=datetime(2026, 11, 9, 12, 0, tzinfo=timezone.get_current_timezone()),
        pk=10,
    )
    earlier_day = Session(performed_date=date(2026, 11, 2), completed_at=None, pk=1)
    earlier_time = Session(
        performed_date=TODAY,
        completed_at=datetime(2026, 11, 9, 11, 0, tzinfo=timezone.get_current_timezone()),
        pk=11,
    )

    assert records.session_is_earlier(earlier_day, current) is True
    assert records.session_is_earlier(earlier_time, current) is True
    assert records.session_is_earlier(current, earlier_time) is False


def test_session_is_earlier_falls_back_to_pk_when_completion_time_is_missing():
    current = Session(performed_date=TODAY, completed_at=None, pk=10)

    assert records.session_is_earlier(
        Session(performed_date=TODAY, completed_at=None, pk=9), current
    )
    assert not records.session_is_earlier(
        Session(performed_date=TODAY, completed_at=None, pk=11), current
    )
