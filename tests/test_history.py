from datetime import date

import pytest
from django.urls import reverse
from freezegun import freeze_time

from apps.plans.models import ScheduledWorkout
from apps.workouts.models import Session, Tag
from apps.workouts.services import history

TODAY = date(2026, 11, 9)


def _session(user, *, day, title, kind=Session.Kind.UNSCHEDULED, workout=None):
    return Session.objects.create(
        user=user,
        kind=kind,
        scheduled_workout=workout,
        title=title,
        performed_date=day,
        status=Session.Status.COMPLETED,
    )


def _scheduled(user, plan, plan_day, day, *, status=ScheduledWorkout.Status.PENDING):
    return ScheduledWorkout.objects.create(
        user=user,
        plan=plan,
        plan_day=plan_day,
        scheduled_date=day,
        status=status,
    )


def _tag(user, name="PT"):
    return Tag.objects.create(user=user, name=name, color="#2B7FFF")


# --- Services ---------------------------------------------------------------


@pytest.mark.django_db
def test_list_sessions_returns_completed_workouts_newest_first(user):
    first = _session(user, day=date(2026, 11, 2), title="First")
    second = _session(user, day=date(2026, 11, 6), title="Second")
    Session.objects.create(
        user=user,
        title="Still running",
        performed_date=date(2026, 11, 9),
        status=Session.Status.IN_PROGRESS,
    )

    sessions = list(history.list_sessions(user))

    assert sessions == [second, first]


@pytest.mark.django_db
def test_filter_sessions_by_tag_and_excluded_tag(user):
    pt = _tag(user, "PT")
    hiit = _tag(user, "HIIT")
    tagged = _session(user, day=date(2026, 11, 6), title="PT")
    tagged.tags.set([pt])
    excluded = _session(user, day=date(2026, 11, 7), title="Both")
    excluded.tags.set([pt, hiit])
    plain = _session(user, day=date(2026, 11, 8), title="Plain")

    assert set(history.list_sessions(user, tag=pt)) == {tagged, excluded}
    assert set(history.list_sessions(user, exclude_tag=hiit)) == {tagged, plain}


@pytest.mark.django_db
def test_filter_sessions_by_plan(user, active_plan, active_plan_day):
    workout = _scheduled(
        user,
        active_plan,
        active_plan_day,
        date(2026, 11, 6),
        status=ScheduledWorkout.Status.COMPLETED,
    )
    scheduled = _session(
        user,
        day=date(2026, 11, 6),
        title="Day A",
        kind=Session.Kind.SCHEDULED,
        workout=workout,
    )
    _session(user, day=date(2026, 11, 7), title="Unscheduled")

    assert list(history.list_sessions(user, plan=active_plan)) == [scheduled]


@pytest.mark.django_db
def test_list_sessions_are_scoped_to_the_user(user, other_user):
    own = _session(user, day=date(2026, 11, 6), title="Mine")
    _session(other_user, day=date(2026, 11, 7), title="Theirs")

    assert list(history.list_sessions(user)) == [own]


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_calendar_month_marks_completed_and_unscheduled_days(user):
    _session(user, day=date(2026, 11, 5), title="Push day")
    _session(
        user,
        day=date(2026, 11, 6),
        title="Day A",
        kind=Session.Kind.SCHEDULED,
    )

    data = history.calendar_month(user, 2026, 11, today=TODAY)

    dots = {
        day["date"]: {dot["status"] for dot in day["dots"]}
        for week in data["weeks"]
        for day in week
    }
    assert dots[date(2026, 11, 5)] == {"UNSCHEDULED"}
    assert dots[date(2026, 11, 6)] == {"COMPLETED"}
    assert data["day_entries"][date(2026, 11, 5)][0]["session"].title == "Push day"


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_made_up_workout_is_marked_on_its_original_date(user, active_plan, active_plan_day):
    workout = _scheduled(
        user,
        active_plan,
        active_plan_day,
        date(2026, 11, 5),
        status=ScheduledWorkout.Status.MADE_UP,
    )
    _session(
        user,
        day=date(2026, 11, 6),
        title="Day A",
        kind=Session.Kind.SCHEDULED,
        workout=workout,
    )

    data = history.calendar_month(user, 2026, 11, today=TODAY)

    dots = {
        day["date"]: {dot["status"] for dot in day["dots"]}
        for week in data["weeks"]
        for day in week
    }
    assert dots[date(2026, 11, 5)] == {"MADE_UP"}
    assert dots[date(2026, 11, 6)] == {"COMPLETED"}
    entry = data["day_entries"][date(2026, 11, 5)][0]
    assert entry["status"] == ScheduledWorkout.Status.MADE_UP
    assert entry["session"] is None


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_calendar_tag_filter_limits_workouts_to_matching_sessions(
    user, active_plan, active_plan_day
):
    pt = _tag(user, "PT")
    matching_workout = _scheduled(
        user,
        active_plan,
        active_plan_day,
        date(2026, 11, 5),
        status=ScheduledWorkout.Status.COMPLETED,
    )
    matching = _session(
        user,
        day=date(2026, 11, 5),
        title="Day A",
        kind=Session.Kind.SCHEDULED,
        workout=matching_workout,
    )
    matching.tags.set([pt])
    _scheduled(
        user,
        active_plan,
        active_plan_day,
        date(2026, 11, 6),
        status=ScheduledWorkout.Status.MISSED,
    )

    data = history.calendar_month(user, 2026, 11, tag=pt, today=TODAY)

    dots = {
        day["date"]: {dot["status"] for dot in day["dots"]}
        for week in data["weeks"]
        for day in week
    }
    assert dots[date(2026, 11, 5)] == {"COMPLETED"}
    assert dots[date(2026, 11, 6)] == set()


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_build_history_defaults_to_today_and_lists_its_entries(user):
    _session(user, day=TODAY, title="Push day")

    context = history.build_history(user, today=TODAY)

    assert context["view"] == "calendar"
    assert context["selected_day"] == TODAY
    assert context["selected_entries"][0]["session"].title == "Push day"
    assert context["month"] == "2026-11"


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_build_history_ignores_a_day_outside_the_month(user):
    _session(user, day=date(2026, 11, 6), title="Push day")

    context = history.build_history(
        user,
        year=2026,
        month=11,
        selected_day="2026-10-05",
        today=TODAY,
    )

    assert context["selected_day"] == TODAY


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_build_history_chooses_the_first_recorded_day_for_another_month(user):
    _session(user, day=date(2026, 9, 15), title="Old workout")

    context = history.build_history(user, year=2026, month=9, today=TODAY)

    assert context["selected_day"] == date(2026, 9, 15)


# --- Views ------------------------------------------------------------------


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_history_calendar_renders_the_month_and_selected_day(client, user):
    session = _session(user, day=TODAY, title="Push day")
    client.force_login(user)

    response = client.get(reverse("history"))

    content = response.content.decode()
    assert response.status_code == 200
    assert "November 2026" in content
    assert "Push day" in content
    assert reverse("session_detail", args=[session.pk]) in content
    assert "Calendar" in content
    assert "List" in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_history_list_shows_completed_sessions(client, user):
    session = _session(user, day=date(2026, 11, 6), title="Push day")
    client.force_login(user)

    response = client.get(reverse("history"), {"view": "list"})

    content = response.content.decode()
    assert response.status_code == 200
    assert "Push day" in content
    assert reverse("session_detail", args=[session.pk]) in content
    assert "Log past" in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_history_filters_by_tag_and_excludes_another(client, user):
    pt = _tag(user, "PT")
    hiit = _tag(user, "HIIT")
    keep = _session(user, day=date(2026, 11, 6), title="Keep me")
    keep.tags.set([pt])
    hide = _session(user, day=date(2026, 11, 7), title="Hide me")
    hide.tags.set([pt, hiit])
    client.force_login(user)

    response = client.get(
        reverse("history"), {"view": "list", "tag": pt.pk, "exclude_tag": hiit.pk}
    )

    content = response.content.decode()
    assert "Keep me" in content
    assert "Hide me" not in content
    assert "Showing PT." in content
    assert "Hiding HIIT." in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_history_filters_by_plan(client, user, active_plan, active_plan_day):
    workout = _scheduled(
        user,
        active_plan,
        active_plan_day,
        date(2026, 11, 6),
        status=ScheduledWorkout.Status.COMPLETED,
    )
    _session(
        user,
        day=date(2026, 11, 6),
        title="Day A",
        kind=Session.Kind.SCHEDULED,
        workout=workout,
    )
    _session(user, day=date(2026, 11, 7), title="Freestyle")
    client.force_login(user)

    response = client.get(reverse("history"), {"view": "list", "plan": active_plan.pk})

    content = response.content.decode()
    assert "Day A" in content
    assert "Freestyle" not in content
    assert f"Plan: {active_plan.name}" in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_history_links_preserve_the_filters(client, user):
    tag = _tag(user, "PT")
    client.force_login(user)

    response = client.get(reverse("history"), {"tag": tag.pk, "month": "2026-11"})

    content = response.content.decode()
    assert f"tag={tag.pk}" in content
    assert "view=list" in content
    assert "month=2026-10" in content
    assert "month=2026-12" in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_history_ignores_an_invalid_month(client, user):
    client.force_login(user)

    response = client.get(reverse("history"), {"month": "not-a-month"})

    assert response.status_code == 200


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_history_does_not_leak_another_users_sessions_or_tags(client, user, other_user):
    _session(other_user, day=TODAY, title="Secret workout")
    Tag.objects.create(user=other_user, name="Secret tag", color="#2B7FFF")
    client.force_login(user)

    response = client.get(reverse("history"), {"view": "list"})

    content = response.content.decode()
    assert "Secret workout" not in content
    assert "Secret tag" not in content
