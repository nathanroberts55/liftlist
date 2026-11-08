from datetime import date

import pytest
from django.urls import reverse
from freezegun import freeze_time
from pytest_django.asserts import assertTemplateUsed

from apps.exercises.models import Exercise
from apps.plans.models import ScheduledWorkout
from apps.workouts.models import Tag

from .factories import add_exercise, make_session

TODAY = date(2026, 11, 9)


def _quads_exercise(muscles):
    return Exercise.objects.create(
        user=None,
        name="Leg Extension",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "kwargs"),
    [
        ("stats", {}),
        ("stats_api_top_set", {}),
        ("stats_api_volume", {}),
    ],
)
def test_stats_routes_require_login(client, url_name, kwargs):
    url = reverse(url_name, kwargs=kwargs)

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={url}"


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_progress_tab_renders_the_weight_chart(client, user, seeded_exercise):
    session = make_session(user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 5}])
    client.force_login(user)

    response = client.get(reverse("stats"))

    assert response.status_code == 200
    assertTemplateUsed(response, "stats/index.html")
    assert response.context["tab"] == "progress"
    assert response.context["exercise"] == seeded_exercise
    assert response.context["chart"]["values"] == [100.0]
    assert response.context["has_chart"] is True
    assert b"Weight over time" in response.content
    assert b"progress-chart-data" in response.content
    assert b"vendor/chart.umd.min.js" in response.content


@pytest.mark.django_db
def test_progress_tab_has_an_empty_state_without_history(client, user):
    client.force_login(user)

    response = client.get(reverse("stats"))

    assert response.status_code == 200
    assert response.context["has_chart"] is False
    assert b"No weight history yet" in response.content
    assert b"vendor/chart.umd.min.js" not in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_progress_tab_scopes_history_to_the_user(client, user, other_user, seeded_exercise):
    session = make_session(other_user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "200", "reps": 5}])
    client.force_login(user)

    response = client.get(reverse("stats"))

    assert response.context["exercise"] is None
    assert response.context["chart"]["values"] == []


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_prs_tab_lists_search_filters_and_expands_records(client, user, muscles, seeded_exercise):
    quads = _quads_exercise(muscles)
    session = make_session(user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 10}], order=0)
    add_exercise(session, quads, [{"weight_lb": "120", "reps": 5}], order=1)
    client.force_login(user)

    response = client.get(reverse("stats"), {"tab": "prs"})

    assert response.status_code == 200
    assert response.context["tab"] == "prs"
    assert [row["exercise"].name for row in response.context["table"]] == [
        "Barbell Bench Press",
        "Leg Extension",
    ]
    assert b"Personal records" in response.content
    assert b"Most reps at each weight" in response.content
    assert b"vendor/chart.umd.min.js" not in response.content

    searched = client.get(reverse("stats"), {"tab": "prs", "q": "bench"})
    assert [row["exercise"].name for row in searched.context["table"]] == ["Barbell Bench Press"]

    filtered = client.get(reverse("stats"), {"tab": "prs", "muscle": "quads"})
    assert [row["exercise"].name for row in filtered.context["table"]] == ["Leg Extension"]


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_volume_tab_renders_sets_and_tonnage(client, user, muscles, seeded_exercise):
    quads = _quads_exercise(muscles)
    session = make_session(user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 10}], order=0)
    add_exercise(session, quads, [{"weight_lb": "120", "reps": 5}], order=1)
    client.force_login(user)

    response = client.get(reverse("stats"), {"tab": "volume"})

    assert response.status_code == 200
    assert response.context["tab"] == "volume"
    assert response.context["metric"] == "sets"
    assert [series["name"] for series in response.context["chart"]["series"]] == [
        "Chest",
        "Quads",
    ]
    assert b"Weekly volume" in response.content
    assert b"volume-chart-data" in response.content
    assert b"vendor/chart.umd.min.js" in response.content

    tonnage = client.get(reverse("stats"), {"tab": "volume", "metric": "tonnage"})
    assert tonnage.context["metric"] == "tonnage"
    assert tonnage.context["chart"]["unit"] == "lb"


@pytest.mark.django_db
def test_volume_tab_has_an_empty_state_without_history(client, user):
    client.force_login(user)

    response = client.get(reverse("stats"), {"tab": "volume"})

    assert response.status_code == 200
    assert response.context["has_chart"] is False
    assert b"No volume yet" in response.content
    assert b"vendor/chart.umd.min.js" not in response.content


@pytest.mark.django_db
def test_invalid_tab_range_and_metric_fall_back_to_defaults(client, user):
    client.force_login(user)

    response = client.get(
        reverse("stats"),
        {"tab": "nonsense", "range": "nonsense", "metric": "nonsense"},
    )

    assert response.context["tab"] == "progress"
    assert response.context["range_key"] == "3m"


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_volume_tab_excludes_the_selected_tag(client, user, seeded_exercise):
    pt = Tag.objects.create(user=user, name="PT")
    tagged = make_session(user, day=TODAY)
    tagged.tags.add(pt)
    add_exercise(tagged, seeded_exercise, [{"weight_lb": "100", "reps": 10}])
    client.force_login(user)

    response = client.get(reverse("stats"), {"tab": "volume", "exclude_tag": str(pt.pk)})

    assert response.context["exclude_tag"] == pt
    assert response.context["chart"]["series"] == []


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_stats_marks_past_pending_workouts_as_missed(client, user, active_plan, active_plan_day):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=date(2026, 11, 8),
    )
    client.force_login(user)

    client.get(reverse("stats"))

    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MISSED


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_top_set_api_returns_json_for_a_visible_exercise(client, user, seeded_exercise):
    session = make_session(user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 5}])
    client.force_login(user)

    response = client.get(
        reverse("stats_api_top_set"),
        {"exercise": seeded_exercise.pk, "range": "all"},
    )

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    data = response.json()
    assert data["values"] == [100.0]
    assert data["labels"] == ["Nov 9"]
    assert data["exercise_id"] == seeded_exercise.pk
    assert data["range"] == "all"


@pytest.mark.django_db
def test_top_set_api_returns_404_for_unknown_or_foreign_exercises(
    client, user, other_user, muscles
):
    foreign = Exercise.objects.create(
        user=other_user,
        name="Secret Lift",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    client.force_login(user)

    assert client.get(reverse("stats_api_top_set"), {"exercise": foreign.pk}).status_code == 404
    assert client.get(reverse("stats_api_top_set"), {"exercise": 99999}).status_code == 404
    assert client.get(reverse("stats_api_top_set")).status_code == 404


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_top_set_api_defaults_an_invalid_range(client, user, seeded_exercise):
    session = make_session(user, day=TODAY)
    add_exercise(session, seeded_exercise, [{"weight_lb": "100", "reps": 5}])
    client.force_login(user)

    response = client.get(
        reverse("stats_api_top_set"),
        {"exercise": seeded_exercise.pk, "range": "nonsense"},
    )

    assert response.json()["range"] == "3m"


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_volume_api_returns_json_and_respects_tag_exclusion(client, user, seeded_exercise):
    pt = Tag.objects.create(user=user, name="PT")
    tagged = make_session(user, day=TODAY)
    tagged.tags.add(pt)
    add_exercise(tagged, seeded_exercise, [{"weight_lb": "100", "reps": 10}])
    client.force_login(user)

    included = client.get(reverse("stats_api_volume"), {"metric": "tonnage"})
    excluded = client.get(
        reverse("stats_api_volume"),
        {"metric": "tonnage", "exclude_tag": str(pt.pk)},
    )

    assert included.status_code == 200
    assert included.headers["Content-Type"].startswith("application/json")
    assert included.json()["series"][0]["total"] == 1000.0
    assert included.json()["unit"] == "lb"
    assert excluded.json()["series"] == []
