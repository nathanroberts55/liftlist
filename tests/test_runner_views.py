import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from freezegun import freeze_time
from pytest_django.asserts import assertTemplateUsed

from apps.exercises.models import Exercise
from apps.plans.models import PlanItem, ScheduledWorkout
from apps.workouts.models import Session, SessionExercise, SetLog
from apps.workouts.services import runner

TODAY = date(2026, 11, 9)


def _scheduled(user, plan, plan_day, day=TODAY):
    return ScheduledWorkout.objects.create(
        user=user,
        plan=plan,
        plan_day=plan_day,
        scheduled_date=day,
    )


def _item(plan_day, exercise, order, **kwargs):
    defaults = {"target_sets": 3, "rep_min": 8, "rep_max": 10, "rest_seconds": 90}
    defaults.update(kwargs)
    return PlanItem.objects.create(
        plan_day=plan_day,
        exercise=exercise,
        order=order,
        **defaults,
    )


def _start(user, workout):
    return runner.start_scheduled_session(user, workout)


def _exercise(muscles, name):
    return Exercise.objects.create(
        user=None,
        name=name,
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )


def test_runner_routes_require_login(client):
    urls = [
        ("get", reverse("session_run", args=[1])),
        ("get", reverse("session_picker", args=[1])),
        ("post", reverse("session_log_set", args=[1])),
        ("post", reverse("session_skip_set", args=[1])),
        ("post", reverse("session_add_set", args=[1])),
        ("post", reverse("session_skip_exercise", args=[1])),
        ("post", reverse("session_add_exercise", args=[1])),
        ("post", reverse("session_reorder", args=[1])),
        ("post", reverse("session_move_exercise", args=[1])),
        ("post", reverse("session_jump", args=[1, 1])),
        ("post", reverse("session_finish", args=[1])),
        ("post", reverse("session_discard", args=[1])),
        ("post", reverse("scheduled_start", args=[1])),
    ]
    for method, url in urls:
        response = getattr(client, method)(url)
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_creates_a_session_and_redirects_to_the_runner(
    client, user, active_plan, active_plan_day, active_plan_item
):
    workout = _scheduled(user, active_plan, active_plan_day)
    client.force_login(user)

    response = client.post(reverse("scheduled_start", args=[workout.pk]))

    session = Session.objects.get(user=user)
    assert response.status_code == 302
    assert response.url == reverse("session_run", args=[session.pk])
    assert session.status == Session.Status.IN_PROGRESS
    assert session.session_exercises.count() == 1


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_resumes_an_existing_session(
    client, user, active_plan, active_plan_day, active_plan_item
):
    workout = _scheduled(user, active_plan, active_plan_day)
    first = _start(user, workout)
    client.force_login(user)

    response = client.post(reverse("scheduled_start", args=[workout.pk]))

    assert response.status_code == 302
    assert response.url == reverse("session_run", args=[first.pk])
    assert Session.objects.filter(user=user).count() == 1


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_is_scoped_to_the_owner(
    client, user, other_user, active_plan, active_plan_day, active_plan_item
):
    workout = _scheduled(user, active_plan, active_plan_day)
    client.force_login(other_user)

    response = client.post(reverse("scheduled_start", args=[workout.pk]))

    assert response.status_code == 404
    assert Session.objects.count() == 0


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_run_page_shows_the_current_set(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    client.force_login(user)

    response = client.get(reverse("session_run", args=[session.pk]))

    assert response.status_code == 200
    assertTemplateUsed(response, "workouts/run.html")
    content = response.content.decode()
    assert "<html" in content
    assert active_plan_item.exercise.name in content
    assert "Exercise 1 of 1" in content
    assert "Set 1 of 4" in content
    assert "Goal 6–8 reps" in content
    assert "Submit" in content
    assert "Add set" in content
    assert "Skip set" in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_run_page_swaps_only_the_runner_for_htmx(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    client.force_login(user)

    response = client.get(
        reverse("session_run", args=[session.pk]),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="runner",
    )

    assert response.status_code == 200
    assertTemplateUsed(response, "workouts/_runner_swap.html")
    assert b"<html" not in response.content
    assert b'id="runner"' in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_boosted_navigation_to_the_runner_returns_a_full_page(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    client.force_login(user)

    response = client.get(
        reverse("session_run", args=[session.pk]),
        HTTP_HX_REQUEST="true",
        HTTP_HX_BOOSTED="true",
    )

    assert response.status_code == 200
    assert b"<html" in response.content
    assert b'id="runner"' in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_run_page_opens_each_panel(client, user, active_plan, active_plan_day, active_plan_item):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    client.force_login(user)

    menu = client.get(reverse("session_run", args=[session.pk]), {"panel": "menu"})
    assert b"Workout menu" in menu.content
    assert b"Reorder exercises" in menu.content

    reorder = client.get(reverse("session_run", args=[session.pk]), {"panel": "reorder"})
    assert b"Reorder exercises" in reorder.content
    assert b"Superset groups move together" in reorder.content

    jump = client.get(reverse("session_run", args=[session.pk]), {"panel": "jump"})
    assert b"Jump to exercise" in jump.content

    picker = client.get(reverse("session_run", args=[session.pk]), {"panel": "add"})
    assert b"Add exercise" in picker.content
    assert b"Search exercises" in picker.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_log_set_persists_and_redirects(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)

    response = client.post(
        reverse("session_log_set", args=[session.pk]),
        {"exercise": session_exercise.pk, "weight_lb": "225", "reps": "8"},
    )

    assert response.status_code == 302
    assert response.url == reverse("session_run", args=[session.pk])
    log = SetLog.objects.get(session_exercise=session_exercise)
    assert log.weight_lb == 225
    assert log.reps == 8


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_log_set_accepts_a_distance_only_cardio_set(
    client, user, active_plan, active_plan_day, muscles
):
    walk = Exercise.objects.create(
        user=None,
        name="Walk",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.CARDIO,
    )
    _item(
        active_plan_day,
        walk,
        order=0,
        target_sets=1,
        rep_min=None,
        rep_max=None,
        target_distance_mi=Decimal("2.48"),
    )
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)

    response = client.post(
        reverse("session_log_set", args=[session.pk]),
        {"exercise": session_exercise.pk, "distance_mi": "2.48"},
    )

    assert response.status_code == 302
    log = SetLog.objects.get(session_exercise=session_exercise)
    assert log.distance_mi == Decimal("2.48")
    assert log.duration_seconds is None


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_rest_screen_shows_a_distance_only_prefill(
    client, user, active_plan, active_plan_day, muscles
):
    walk = Exercise.objects.create(
        user=None,
        name="Walk",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.CARDIO,
    )
    _item(
        active_plan_day,
        walk,
        order=0,
        target_sets=2,
        rep_min=None,
        rep_max=None,
        target_distance_mi=Decimal("2.48"),
        rest_seconds=60,
    )
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)

    response = client.post(
        reverse("session_log_set", args=[session.pk]),
        {"exercise": session_exercise.pk, "distance_mi": "2.48"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="runner",
    )

    assert response.status_code == 200
    assert b"2.48 mi" in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_log_set_htmx_returns_the_rest_screen(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)

    response = client.post(
        reverse("session_log_set", args=[session.pk]),
        {"exercise": session_exercise.pk, "weight_lb": "225", "reps": "8"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="runner",
    )

    assert response.status_code == 200
    assert b"<html" not in response.content
    assert b"Rest" in response.content
    assert b"Skip" in response.content
    assert b"Set 2 of 4" in response.content
    assert b"runnerTimer(120, true)" in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_rest_screen_respects_the_timer_sound_setting(
    client, user, active_plan, active_plan_day, active_plan_item
):
    user.settings.timer_sound = False
    user.settings.save(update_fields=["timer_sound"])
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)

    response = client.post(
        reverse("session_log_set", args=[session.pk]),
        {"exercise": session_exercise.pk, "weight_lb": "225", "reps": "8"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="runner",
    )

    assert response.status_code == 200
    assert b"runnerTimer(120, false)" in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_log_set_is_idempotent_for_the_hidden_client_id(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)
    client_id = str(uuid.uuid4())

    for _ in range(2):
        client.post(
            reverse("session_log_set", args=[session.pk]),
            {
                "exercise": session_exercise.pk,
                "weight_lb": "225",
                "reps": "8",
                "client_id": client_id,
            },
        )

    assert SetLog.objects.count() == 1


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_invalid_set_keeps_the_values_and_offers_a_retry(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)

    response = client.post(
        reverse("session_log_set", args=[session.pk]),
        {"exercise": session_exercise.pk, "weight_lb": "", "reps": "8"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="runner",
    )

    assert response.status_code == 200
    assert b"Retry save" in response.content
    assert b"Couldn" in response.content
    assert SetLog.objects.count() == 0


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_invalid_set_without_javascript_redirects_with_a_message(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)

    response = client.post(
        reverse("session_log_set", args=[session.pk]),
        {"exercise": session_exercise.pk, "weight_lb": "", "reps": "8"},
        follow=True,
    )

    assert response.status_code == 200
    assert b"Couldn" in response.content
    assert SetLog.objects.count() == 0


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_skip_set_and_add_set_view_actions(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)

    client.post(
        reverse("session_skip_set", args=[session.pk]),
        {"exercise": session_exercise.pk},
    )
    assert SetLog.objects.get(session_exercise=session_exercise).status == SetLog.Status.SKIPPED

    client.post(
        reverse("session_add_set", args=[session.pk]),
        {"exercise": session_exercise.pk},
    )
    session_exercise.refresh_from_db()
    assert session_exercise.target_sets == 5


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_skip_exercise_view_marks_the_remaining_sets(
    client, user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(user)

    client.post(
        reverse("session_skip_exercise", args=[session.pk]),
        {"exercise": session_exercise.pk},
    )

    session_exercise.refresh_from_db()
    assert session_exercise.status == SessionExercise.Status.SKIPPED
    assert SetLog.objects.filter(session_exercise=session_exercise).count() == 4


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_add_exercise_view_appends_the_choice(
    client, user, active_plan, active_plan_day, active_plan_item, muscles
):
    extra = _exercise(muscles, "Cable Fly")
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    client.force_login(user)

    response = client.post(
        reverse("session_add_exercise", args=[session.pk]),
        {"exercise": extra.pk},
    )

    assert response.status_code == 302
    assert session.session_exercises.filter(exercise=extra).exists()


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_picker_filters_exercises(
    client, user, active_plan, active_plan_day, active_plan_item, muscles
):
    _exercise(muscles, "Cable Fly")
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    client.force_login(user)

    response = client.get(
        reverse("session_picker", args=[session.pk]),
        {"q": "Cable"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"Cable Fly" in response.content
    assert active_plan_item.exercise.name.encode() not in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_reorder_move_and_jump_views(
    client, user, active_plan, active_plan_day, active_plan_item, muscles
):
    second_exercise = _exercise(muscles, "Leg Press")
    third_exercise = _exercise(muscles, "Cable Fly")
    _item(active_plan_day, second_exercise, order=1)
    _item(active_plan_day, third_exercise, order=2)
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    client.force_login(user)
    first = session.session_exercises.get(exercise=active_plan_item.exercise)
    second = session.session_exercises.get(exercise=second_exercise)
    third = session.session_exercises.get(exercise=third_exercise)

    response = client.post(
        reverse("session_reorder", args=[session.pk]),
        {"ordered_ids": f"{second.pk},{third.pk},{first.pk}"},
    )
    assert response.status_code == 302
    first.refresh_from_db()
    second.refresh_from_db()
    third.refresh_from_db()
    assert [second.order, third.order, first.order] == [0, 1, 2]

    client.post(
        reverse("session_move_exercise", args=[session.pk]),
        {"exercise": third.pk, "direction": "down"},
    )
    third.refresh_from_db()
    second.refresh_from_db()
    first.refresh_from_db()
    assert [second.order, first.order, third.order] == [0, 1, 2]

    runner.log_set(session, second, {"weight_lb": "135", "reps": "8"})
    client.post(reverse("session_jump", args=[session.pk, third.pk]))
    first.refresh_from_db()
    third.refresh_from_db()
    second.refresh_from_db()
    assert [second.order, third.order, first.order] == [0, 1, 2]


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_finish_shows_the_completion_card(
    client, user, active_plan, active_plan_day, active_plan_item
):
    workout = _scheduled(user, active_plan, active_plan_day)
    session = _start(user, workout)
    client.force_login(user)

    response = client.post(reverse("session_finish", args=[session.pk]))

    session.refresh_from_db()
    workout.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("session_run", args=[session.pk])
    assert session.status == Session.Status.COMPLETED
    assert workout.status == ScheduledWorkout.Status.COMPLETED

    page = client.get(response.url)
    assert b"Workout complete" in page.content
    assert b"Total volume" in page.content
    assert b"Muscles worked" in page.content
    assert b"Plan adherence" in page.content
    assert b"Done" in page.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_finish_can_return_to_today(client, user, active_plan, active_plan_day, active_plan_item):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    client.force_login(user)

    response = client.post(
        reverse("session_finish", args=[session.pk]),
        {"next": "today"},
    )

    assert response.status_code == 302
    assert response.url == reverse("today")


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_discard_requires_confirmation_then_deletes(
    client, user, active_plan, active_plan_day, active_plan_item
):
    workout = _scheduled(user, active_plan, active_plan_day, day=date(2026, 11, 2))
    session = _start(user, workout)
    client.force_login(user)

    page = client.post(reverse("session_discard", args=[session.pk]))
    assert page.status_code == 200
    assert b"Discard workout?" in page.content
    assert Session.objects.filter(pk=session.pk).exists()

    response = client.post(
        reverse("session_discard", args=[session.pk]),
        {"confirm": "1"},
    )
    assert response.status_code == 302
    assert response.url == reverse("today")
    assert Session.objects.filter(pk=session.pk).exists() is False
    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MISSED


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_runner_is_scoped_to_the_owner(
    client, user, other_user, active_plan, active_plan_day, active_plan_item
):
    session = _start(user, _scheduled(user, active_plan, active_plan_day))
    session_exercise = session.session_exercises.get()
    client.force_login(other_user)

    assert client.get(reverse("session_run", args=[session.pk])).status_code == 404
    assert (
        client.post(
            reverse("session_log_set", args=[session.pk]),
            {"exercise": session_exercise.pk, "weight_lb": "225", "reps": "8"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            reverse("session_finish", args=[session.pk]),
        ).status_code
        == 404
    )
    assert (
        client.post(
            reverse("session_discard", args=[session.pk]),
            {"confirm": "1"},
        ).status_code
        == 404
    )
