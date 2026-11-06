from datetime import date

import pytest
from django.urls import reverse
from freezegun import freeze_time
from pytest_django.asserts import assertTemplateUsed

from apps.plans.models import PlanDay, PlanItem, ScheduledWorkout, Weekday
from apps.workouts.models import Session, SessionExercise, SetLog
from apps.workouts.services import runner

TODAY = date(2026, 11, 9)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_prompts_for_a_plan_when_none_is_active(client, user):
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert b"No active plan" in response.content
    assert b"Create plan" in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_shows_a_rest_day_when_nothing_is_scheduled(client, user, active_plan):
    PlanDay.objects.create(
        plan=active_plan,
        name="Day B – Upper",
        weekday=Weekday.TUESDAY,
        order=Weekday.TUESDAY,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert b"Rest day" in response.content
    assert b"No workout scheduled today" in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_shows_the_scheduled_workout_and_targets(
    client, user, active_plan, active_plan_day, active_plan_item
):
    ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert active_plan_day.name.encode() in response.content
    assert active_plan_item.exercise.name.encode() in response.content
    assert "4 × 6" in response.content.decode()
    assert b"Start workout" in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_offers_mark_as_missed(client, user, active_plan, active_plan_day):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert b"Mark as missed" in response.content
    assert reverse("scheduled_mark_missed", args=[workout.pk]).encode() in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_mark_missed_htmx_swaps_the_today_content(client, user, active_plan, active_plan_day):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    client.force_login(user)

    response = client.post(
        reverse("scheduled_mark_missed", args=[workout.pk]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assertTemplateUsed(response, "core/_today_swap.html")
    assertTemplateUsed(response, "core/_today_content.html")
    assert b"<html" not in response.content
    assert b'id="today-content"' in response.content
    assert b"Marked as missed." in response.content
    assert b"MISSED" in response.content
    assert b"Marked missed." in response.content
    assert b'hx-swap-oob="true"' in response.content

    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MISSED
    assert workout.marked_missed_manually is True


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_mark_missed_is_scoped_to_the_owner(
    client, user, other_user, active_plan, active_plan_day
):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    client.force_login(other_user)

    response = client.post(
        reverse("scheduled_mark_missed", args=[workout.pk]),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 404


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_lists_catch_up_workouts(client, user, active_plan, active_plan_day):
    ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=date(2026, 11, 2),
    )
    ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert b"Catch up" in response.content
    assert b"Missed" in response.content
    # sync_statuses marks the overdue row before rendering.
    assert (
        ScheduledWorkout.objects.get(scheduled_date=date(2026, 11, 2)).status
        == ScheduledWorkout.Status.MISSED
    )


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_shows_the_week_strip(client, user, active_plan, active_plan_day):
    ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
        status=ScheduledWorkout.Status.COMPLETED,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert b"This week" in response.content
    assert b">M<" in response.content
    assert b">W<" in response.content
    assert b">F<" in response.content
    assert b"bg-success" in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_shows_week_progress(client, user, active_plan, active_plan_day):
    ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert b"Week 2 of 4" in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_marks_a_missed_workout_without_the_miss_button(
    client, user, active_plan, active_plan_day
):
    ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
        status=ScheduledWorkout.Status.MISSED,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert b"Marked missed" in response.content
    assert b"Mark as missed" not in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_lists_items_in_order(
    client, user, active_plan, active_plan_day, active_plan_item, muscles
):
    from apps.exercises.models import Exercise

    second_exercise = Exercise.objects.create(
        user=None,
        name="Leg Press",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    PlanItem.objects.create(
        plan_day=active_plan_day,
        exercise=second_exercise,
        order=1,
        target_sets=3,
        rep_min=10,
        rep_max=12,
    )
    ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    content = response.content.decode()
    assert content.index(active_plan_item.exercise.name) < content.index(second_exercise.name)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_shows_a_resume_banner_for_an_in_progress_session(
    client, user, active_plan, active_plan_day, active_plan_item
):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    session = runner.start_scheduled_session(user, workout)
    client.force_login(user)

    response = client.get(reverse("today"))

    content = response.content.decode()
    assert "Workout in progress" in content
    assert "Resume workout" in content
    assert reverse("session_run", args=[session.pk]) in content
    assert reverse("session_finish", args=[session.pk]) in content
    assert reverse("session_discard", args=[session.pk]) in content
    assert "Start workout" not in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_links_to_a_finished_workout(
    client, user, active_plan, active_plan_day, active_plan_item
):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    session = runner.start_scheduled_session(user, workout)
    runner.finish_session(session)
    client.force_login(user)

    response = client.get(reverse("today"))

    content = response.content.decode()
    assert "Nice work. This workout is saved." in content
    assert "View workout" in content
    assert reverse("session_run", args=[session.pk]) in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_starts_a_missed_workout_as_a_catch_up(
    client, user, active_plan, active_plan_day, active_plan_item
):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
        status=ScheduledWorkout.Status.MISSED,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    assert b"Start catch-up" in response.content
    assert reverse("scheduled_start", args=[workout.pk]).encode() in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_flags_an_exercise_ready_to_increase(
    client, user, active_plan, active_plan_day, active_plan_item
):
    past = Session.objects.create(
        user=user,
        kind=Session.Kind.SCHEDULED,
        plan_day=active_plan_day,
        title="Day A – Lower",
        performed_date=date(2026, 11, 2),
        status=Session.Status.COMPLETED,
    )
    session_exercise = SessionExercise.objects.create(
        session=past,
        exercise=active_plan_item.exercise,
        order=0,
        target_sets=4,
        planned_sets=4,
        rep_min=6,
        rep_max=8,
    )
    for number in range(1, 5):
        SetLog.objects.create(
            session_exercise=session_exercise,
            set_number=number,
            weight_lb=185,
            reps=8,
        )
    ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    assert b"Increase" in response.content
