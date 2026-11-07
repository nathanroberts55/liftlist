import re
from datetime import date, datetime

import pytest
from django.urls import reverse
from freezegun import freeze_time

from apps.plans.models import ScheduledWorkout
from apps.workouts.models import Session, SessionExercise, SetLog, Tag
from apps.workouts.services import sessions as session_services
from apps.workouts.services import tags as tag_services

TODAY = date(2026, 11, 9)


def _completed_session(user, exercise, *, day=TODAY, title="Push day", sets=2):
    session = Session.objects.create(
        user=user,
        kind=Session.Kind.UNSCHEDULED,
        title=title,
        performed_date=day,
        status=Session.Status.COMPLETED,
    )
    session_exercise = SessionExercise.objects.create(
        session=session,
        exercise=exercise,
        order=0,
        target_sets=3,
        planned_sets=3,
        rep_min=8,
        rep_max=10,
        rest_seconds=90,
    )
    for number in range(1, sets + 1):
        SetLog.objects.create(
            session_exercise=session_exercise,
            set_number=number,
            weight_lb=225,
            reps=8,
        )
    return session, session_exercise


def _item_data(exercise, index=0, **overrides):
    data = {
        "exercise": str(exercise.pk),
        "target_sets": "3",
        "rep_min": "8",
        "rep_max": "10",
        "rest_seconds": "90",
    }
    data.update(overrides)
    return {f"items-{index}-{key}": value for key, value in data.items()}


def _formset_data(*rows):
    data = {
        "items-TOTAL_FORMS": str(len(rows)),
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
    }
    for index, row in enumerate(rows):
        data.update(_item_data(row, index=index))
    return data


# --- Services ---------------------------------------------------------------


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_unscheduled_session_snapshots_the_exercises(user, seeded_exercise):
    session = session_services.start_unscheduled_session(
        user,
        title="  Push day  ",
        items=[
            {
                "exercise": seeded_exercise,
                "target_sets": 4,
                "rep_min": 6,
                "rep_max": 8,
                "rest_seconds": 120,
            }
        ],
    )

    assert session.title == "Push day"
    assert session.kind == Session.Kind.UNSCHEDULED
    assert session.status == Session.Status.IN_PROGRESS
    assert session.performed_date == TODAY
    exercise = session.session_exercises.get()
    assert exercise.exercise == seeded_exercise
    assert exercise.target_sets == 4
    assert exercise.planned_sets == 4
    assert exercise.rep_min == 6


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_unscheduled_session_requires_an_exercise(user):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        session_services.start_unscheduled_session(user, title="Push day", items=[])


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_start_unscheduled_session_refuses_a_second_in_progress_workout(user, seeded_exercise):
    from django.core.exceptions import ValidationError

    session_services.start_unscheduled_session(
        user,
        title="First",
        items=[
            {
                "exercise": seeded_exercise,
                "target_sets": 3,
                "rep_min": 8,
                "rep_max": 10,
                "rest_seconds": 90,
            }
        ],
    )

    with pytest.raises(ValidationError):
        session_services.start_unscheduled_session(
            user,
            title="Second",
            items=[
                {
                    "exercise": seeded_exercise,
                    "target_sets": 3,
                    "rep_min": 8,
                    "rep_max": 10,
                    "rest_seconds": 90,
                }
            ],
        )


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_create_retro_session_records_time_and_duration(user, seeded_exercise):
    session = session_services.create_retro_session(
        user,
        title="PT session",
        performed_date=date(2026, 11, 7),
        start_time=datetime(2026, 11, 7, 9, 30).time(),
        duration_seconds=45 * 60,
        items=[
            {
                "exercise": seeded_exercise,
                "target_sets": 3,
                "rep_min": 8,
                "rep_max": 10,
                "rest_seconds": 90,
            }
        ],
    )

    assert session.is_retro_log
    assert session.is_completed
    assert session.duration_seconds == 45 * 60
    assert session.started_at is not None
    assert session.completed_at is not None
    assert session.elapsed_label == "45:00"


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_create_retro_session_rejects_a_future_date(user, seeded_exercise):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        session_services.create_retro_session(
            user,
            title="PT session",
            performed_date=date(2026, 11, 10),
            items=[
                {
                    "exercise": seeded_exercise,
                    "target_sets": 3,
                    "rep_min": 8,
                    "rep_max": 10,
                    "rest_seconds": 90,
                }
            ],
        )


# --- Session creation views -------------------------------------------------


@pytest.mark.django_db
def test_session_routes_require_login(client):
    urls = [
        ("get", reverse("session_new")),
        ("post", reverse("session_new")),
        ("get", reverse("session_log")),
        ("post", reverse("session_log")),
        ("get", reverse("session_detail", args=[1])),
        ("get", reverse("session_edit", args=[1])),
        ("post", reverse("session_edit", args=[1])),
        ("get", reverse("session_delete", args=[1])),
        ("post", reverse("session_delete", args=[1])),
        ("post", reverse("set_add", args=[1])),
        ("get", reverse("set_row", args=[1])),
        ("get", reverse("set_edit", args=[1])),
        ("post", reverse("set_edit", args=[1])),
        ("get", reverse("set_delete", args=[1])),
        ("post", reverse("set_delete", args=[1])),
        ("get", reverse("history")),
    ]
    for method, url in urls:
        response = getattr(client, method)(url)
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_new_page_shows_tag_and_exercise_rows(client, user, seeded_exercise):
    tag = Tag.objects.create(user=user, name="PT", color=tag_services.DEFAULT_TAG_COLOR)
    client.force_login(user)

    response = client.get(reverse("session_new"))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Unscheduled session" in content
    assert "Start workout" in content
    assert seeded_exercise.name in content
    assert tag.name in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_new_pre_checks_default_tags(client, user, seeded_exercise):
    tag = Tag.objects.create(user=user, name="PT", color=tag_services.DEFAULT_TAG_COLOR)
    tag_services.set_default_tags(user, [tag.pk])
    client.force_login(user)

    response = client.get(reverse("session_new"))

    content = response.content.decode()
    assert re.search(rf'value="{tag.pk}"[^>]*checked', content)


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_new_attaches_selected_tags(client, user, seeded_exercise):
    tag = Tag.objects.create(user=user, name="PT", color=tag_services.DEFAULT_TAG_COLOR)
    client.force_login(user)
    data = {"title": "Push day", "tags": [tag.pk], **_formset_data(seeded_exercise)}

    response = client.post(reverse("session_new"), data)

    session = Session.objects.get(user=user)
    assert response.status_code == 302
    assert list(session.tags.all()) == [tag]


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_new_post_starts_a_session_and_redirects_to_the_runner(
    client, user, seeded_exercise
):
    client.force_login(user)
    data = {"title": "Push day", **_formset_data(seeded_exercise)}

    response = client.post(reverse("session_new"), data)

    session = Session.objects.get(user=user)
    assert response.status_code == 302
    assert response.url == reverse("session_run", args=[session.pk])
    assert session.status == Session.Status.IN_PROGRESS
    assert session.session_exercises.count() == 1


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_new_add_row_re_renders_with_the_typed_values(client, user, seeded_exercise):
    client.force_login(user)
    data = {"title": "Push day", "add_row": "1", **_formset_data(seeded_exercise)}
    data["items-TOTAL_FORMS"] = "1"

    response = client.post(reverse("session_new"), data)

    content = response.content.decode()
    assert response.status_code == 200
    assert "Push day" in content
    assert 'value="Push day"' in content
    assert "items-1-exercise" in content
    assert not Session.objects.filter(user=user).exists()


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_new_requires_at_least_one_exercise(client, user, seeded_exercise):
    client.force_login(user)
    data = {
        "title": "Push day",
        "items-TOTAL_FORMS": "2",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
    }

    response = client.post(reverse("session_new"), data)

    assert response.status_code == 200
    assert b"Add at least one exercise." in response.content
    assert not Session.objects.filter(user=user).exists()


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_log_page_defaults_to_today(client, user):
    client.force_login(user)

    response = client.get(reverse("session_log"))

    assert response.status_code == 200
    assert b"Log past workout" in response.content
    assert b'value="2026-11-09"' in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_log_post_creates_a_completed_retro_session(client, user, seeded_exercise):
    client.force_login(user)
    data = {
        "title": "PT session",
        "performed_date": "2026-11-07",
        "duration_minutes": "45",
        **_formset_data(seeded_exercise),
    }

    response = client.post(reverse("session_log"), data)

    session = Session.objects.get(user=user)
    assert response.status_code == 302
    assert response.url == reverse("session_detail", args=[session.pk])
    assert session.is_completed
    assert session.is_retro_log
    assert session.performed_date == date(2026, 11, 7)
    assert session.duration_seconds == 45 * 60


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_log_rejects_a_future_date(client, user, seeded_exercise):
    client.force_login(user)
    data = {
        "title": "PT session",
        "performed_date": "2026-11-10",
        **_formset_data(seeded_exercise),
    }

    response = client.post(reverse("session_log"), data)

    assert response.status_code == 200
    assert b"Pick today or a past date." in response.content
    assert not Session.objects.filter(user=user).exists()


# --- Session detail and editing ---------------------------------------------


@pytest.mark.django_db
def test_session_detail_lists_sets_and_add_forms(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise)
    client.force_login(user)

    response = client.get(reverse("session_detail", args=[session.pk]))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Push day" in content
    assert seeded_exercise.name in content
    assert "Set 1" in content
    assert "225" in content
    assert reverse("set_edit", args=[exercise.sets.first().pk]) in content
    assert reverse("set_add", args=[session.pk]) in content
    assert "Add a set" in content


@pytest.mark.django_db
def test_session_detail_for_an_in_progress_session_links_to_the_runner(
    client, user, seeded_exercise
):
    session = Session.objects.create(
        user=user,
        kind=Session.Kind.UNSCHEDULED,
        title="Push day",
        performed_date=TODAY,
        status=Session.Status.IN_PROGRESS,
    )
    SessionExercise.objects.create(
        session=session,
        exercise=seeded_exercise,
        order=0,
        target_sets=3,
        planned_sets=3,
        rep_min=8,
        rep_max=10,
    )
    client.force_login(user)

    response = client.get(reverse("session_detail", args=[session.pk]))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Resume workout" in content
    assert reverse("session_run", args=[session.pk]) in content
    assert "Add a set" not in content


@pytest.mark.django_db
def test_session_detail_is_scoped_to_the_user(client, user, other_user, seeded_exercise):
    session, _ = _completed_session(other_user, seeded_exercise)
    client.force_login(user)

    response = client.get(reverse("session_detail", args=[session.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_edit_updates_title_date_and_tags(client, user, seeded_exercise):
    session, _ = _completed_session(user, seeded_exercise)
    tag = Tag.objects.create(user=user, name="PT", color=tag_services.DEFAULT_TAG_COLOR)
    client.force_login(user)

    response = client.post(
        reverse("session_edit", args=[session.pk]),
        {
            "title": "Push day v2",
            "performed_date": "2026-11-08",
            "tags": [tag.pk],
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("session_detail", args=[session.pk])
    session.refresh_from_db()
    assert session.title == "Push day v2"
    assert session.performed_date == date(2026, 11, 8)
    assert list(session.tags.all()) == [tag]


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_edit_rejects_a_future_date(client, user, seeded_exercise):
    session, _ = _completed_session(user, seeded_exercise)
    client.force_login(user)

    response = client.post(
        reverse("session_edit", args=[session.pk]),
        {"title": "Push day", "performed_date": "2026-11-10"},
    )

    assert response.status_code == 200
    assert b"Pick today or a past date." in response.content
    session.refresh_from_db()
    assert session.performed_date == TODAY


@pytest.mark.django_db
def test_cannot_edit_another_users_session(client, user, other_user, seeded_exercise):
    session, _ = _completed_session(other_user, seeded_exercise)
    client.force_login(user)

    response = client.get(reverse("session_edit", args=[session.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_changing_a_scheduled_session_date_marks_it_made_up(
    client, user, active_plan, active_plan_day
):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
        status=ScheduledWorkout.Status.COMPLETED,
    )
    session = Session.objects.create(
        user=user,
        kind=Session.Kind.SCHEDULED,
        scheduled_workout=workout,
        plan_day=active_plan_day,
        title="Day A",
        performed_date=TODAY,
        status=Session.Status.COMPLETED,
    )
    client.force_login(user)

    response = client.post(
        reverse("session_edit", args=[session.pk]),
        {"title": "Day A", "performed_date": "2026-11-08"},
    )

    assert response.status_code == 302
    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MADE_UP


@pytest.mark.django_db
def test_session_delete_page_asks_for_confirmation(client, user, seeded_exercise):
    session, _ = _completed_session(user, seeded_exercise)
    client.force_login(user)

    response = client.get(reverse("session_delete", args=[session.pk]))

    assert response.status_code == 200
    assert b"Delete workout?" in response.content
    assert Session.objects.filter(pk=session.pk).exists()


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_session_delete_removes_the_session_and_reopens_the_scheduled_workout(
    client, user, active_plan, active_plan_day
):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
        status=ScheduledWorkout.Status.COMPLETED,
    )
    session = Session.objects.create(
        user=user,
        kind=Session.Kind.SCHEDULED,
        scheduled_workout=workout,
        plan_day=active_plan_day,
        title="Day A",
        performed_date=TODAY,
        status=Session.Status.COMPLETED,
    )
    client.force_login(user)

    response = client.post(reverse("session_delete", args=[session.pk]), {"confirm": "1"})

    assert response.status_code == 302
    assert response.url == reverse("history")
    assert not Session.objects.filter(pk=session.pk).exists()
    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.PENDING


@pytest.mark.django_db
def test_cannot_delete_another_users_session(client, user, other_user, seeded_exercise):
    session, _ = _completed_session(other_user, seeded_exercise)
    client.force_login(user)

    response = client.post(reverse("session_delete", args=[session.pk]), {"confirm": "1"})

    assert response.status_code == 404
    assert Session.objects.filter(pk=session.pk).exists()


# --- Set editing ------------------------------------------------------------


@pytest.mark.django_db
def test_add_manual_set_appends_the_next_number(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=2)
    client.force_login(user)

    response = client.post(
        reverse("set_add", args=[session.pk]),
        {"exercise": exercise.pk, "weight_lb": "230", "reps": "9"},
    )

    assert response.status_code == 302
    assert response.url == reverse("session_detail", args=[session.pk])
    log = exercise.sets.get(set_number=3)
    assert log.weight_lb == 230
    assert log.reps == 9
    assert log.is_extra is False
    exercise.refresh_from_db()
    assert exercise.status == SessionExercise.Status.DONE


@pytest.mark.django_db
def test_add_manual_set_marks_sets_beyond_the_plan_as_extra(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=3)
    client.force_login(user)

    client.post(
        reverse("set_add", args=[session.pk]),
        {"exercise": exercise.pk, "weight_lb": "225", "reps": "8"},
    )

    log = exercise.sets.get(set_number=4)
    assert log.is_extra is True


@pytest.mark.django_db
def test_add_manual_set_rejects_invalid_values(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=2)
    client.force_login(user)

    response = client.post(
        reverse("set_add", args=[session.pk]),
        {"exercise": exercise.pk, "weight_lb": "", "reps": "8"},
        follow=True,
    )

    assert b"Enter weight." in response.content
    assert exercise.sets.count() == 2


@pytest.mark.django_db
def test_set_edit_page_is_full_page_without_htmx(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=1)
    log = exercise.sets.get()
    client.force_login(user)

    response = client.get(reverse("set_edit", args=[log.pk]))

    assert response.status_code == 200
    assert b"Save set" in response.content
    assert b"Edit set" in response.content


@pytest.mark.django_db
def test_set_edit_returns_only_the_row_for_an_htmx_target(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=1)
    log = exercise.sets.get()
    client.force_login(user)

    response = client.get(
        reverse("set_edit", args=[log.pk]),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET=f"set-{log.pk}",
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert f'id="set-{log.pk}"' in content
    assert "Save" in content
    assert "<html" not in content


@pytest.mark.django_db
def test_set_edit_updates_the_set_without_htmx(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=1)
    log = exercise.sets.get()
    client.force_login(user)

    response = client.post(
        reverse("set_edit", args=[log.pk]),
        {"weight_lb": "245", "reps": "5", "difficulty": "9"},
    )

    assert response.status_code == 302
    assert response.url == reverse("session_detail", args=[session.pk])
    log.refresh_from_db()
    assert log.weight_lb == 245
    assert log.reps == 5
    assert log.difficulty == 9


@pytest.mark.django_db
def test_set_edit_swaps_the_row_for_an_htmx_target(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=1)
    log = exercise.sets.get()
    client.force_login(user)

    response = client.post(
        reverse("set_edit", args=[log.pk]),
        {"weight_lb": "245", "reps": "5"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET=f"set-{log.pk}",
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert f'id="set-{log.pk}"' in content
    assert "245" in content
    assert "<html" not in content


@pytest.mark.django_db
def test_set_row_partial_keeps_the_edit_actions(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=1)
    log = exercise.sets.get()
    client.force_login(user)

    response = client.get(reverse("set_row", args=[log.pk]))

    content = response.content.decode()
    assert response.status_code == 200
    assert reverse("set_edit", args=[log.pk]) in content
    assert reverse("set_delete", args=[log.pk]) in content


@pytest.mark.django_db
def test_set_delete_page_asks_for_confirmation(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=1)
    log = exercise.sets.get()
    client.force_login(user)

    response = client.get(reverse("set_delete", args=[log.pk]))

    assert response.status_code == 200
    assert b"Delete set?" in response.content
    assert SetLog.objects.filter(pk=log.pk).exists()


@pytest.mark.django_db
def test_set_delete_renumbers_the_remaining_sets(client, user, seeded_exercise):
    session, exercise = _completed_session(user, seeded_exercise, sets=3)
    log = exercise.sets.get(set_number=2)
    client.force_login(user)

    response = client.post(reverse("set_delete", args=[log.pk]), {"confirm": "1"})

    assert response.status_code == 302
    assert response.url == reverse("session_detail", args=[session.pk])
    remaining = list(exercise.sets.order_by("set_number"))
    assert [item.set_number for item in remaining] == [1, 2]
    assert remaining[1].weight_lb == 225
    exercise.refresh_from_db()
    assert exercise.status == SessionExercise.Status.IN_PROGRESS


@pytest.mark.django_db
def test_cannot_edit_or_delete_another_users_set(client, user, other_user, seeded_exercise):
    session, exercise = _completed_session(other_user, seeded_exercise, sets=1)
    log = exercise.sets.get()
    client.force_login(user)

    assert client.get(reverse("set_edit", args=[log.pk])).status_code == 404
    assert client.post(reverse("set_delete", args=[log.pk]), {"confirm": "1"}).status_code == 404
    assert SetLog.objects.filter(pk=log.pk).exists()


# --- Today entry points -----------------------------------------------------


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_offers_unscheduled_entry_points(client, user):
    client.force_login(user)

    response = client.get(reverse("today"))

    content = response.content.decode()
    assert "On your own" in content
    assert reverse("session_new") in content
    assert reverse("session_log") in content
    assert "Plan &amp; start a workout" in content
    assert "Log a past workout" in content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_hides_plan_and_start_while_a_workout_is_in_progress(client, user, seeded_exercise):
    Session.objects.create(
        user=user,
        kind=Session.Kind.UNSCHEDULED,
        title="Push day",
        performed_date=TODAY,
        status=Session.Status.IN_PROGRESS,
    )
    client.force_login(user)

    response = client.get(reverse("today"))

    content = response.content.decode()
    assert "On your own" in content
    assert reverse("session_new") not in content
    assert "Finish or discard your current workout before starting another." in content
    assert reverse("session_log") in content
