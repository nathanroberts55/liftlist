from datetime import date

import pytest
from django.urls import reverse
from freezegun import freeze_time
from pytest_django.asserts import assertTemplateUsed

from apps.exercises.models import Exercise
from apps.plans.models import Plan, PlanDay, PlanItem, ScheduledWorkout, Weekday

TODAY = date(2026, 11, 9)


def _second_plan_item(plan_day, muscles, *, name="Barbell Row", order=1):
    exercise = Exercise.objects.create(
        user=None,
        name=name,
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    return PlanItem.objects.create(
        plan_day=plan_day,
        exercise=exercise,
        order=order,
        target_sets=3,
        rep_min=8,
        rep_max=10,
    )


def test_plan_routes_require_login(client):
    for url in (
        reverse("plans"),
        reverse("plan_new"),
        reverse("plan_detail", args=[1]),
    ):
        response = client.get(url)

        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_plan_list_shows_grouped_plans(client, user, plan, active_plan):
    client.force_login(user)

    response = client.get(reverse("plans"))

    assert response.status_code == 200
    assert plan.name.encode() in response.content
    assert active_plan.name.encode() in response.content
    assert b"Active" in response.content
    assert b"Drafts" in response.content


@pytest.mark.django_db
def test_plan_list_shows_the_empty_state(client, user):
    client.force_login(user)

    response = client.get(reverse("plans"))

    assert b"No plans yet" in response.content


@pytest.mark.django_db
def test_plan_new_creates_a_draft(client, user):
    client.force_login(user)

    response = client.post(
        reverse("plan_new"),
        {
            "name": "Push/Pull/Legs",
            "split_type": Plan.SplitType.PPL,
            "start_date": "2026-11-09",
            "length_weeks": "6",
        },
    )

    plan = Plan.objects.get(user=user, name="Push/Pull/Legs")
    assert response.status_code == 302
    assert response.url == reverse("plan_detail", args=[plan.pk])
    assert plan.is_draft
    assert plan.length_weeks == 6


@pytest.mark.django_db
def test_plan_new_rejects_an_empty_name(client, user):
    client.force_login(user)

    response = client.post(
        reverse("plan_new"),
        {"name": "", "split_type": Plan.SplitType.CUSTOM, "start_date": "2026-11-09"},
    )

    assert response.status_code == 200
    assert b"Enter a plan name" in response.content
    assert Plan.objects.count() == 0


@pytest.mark.django_db
def test_plan_detail_shows_days_and_items(client, user, plan, plan_day, plan_item):
    client.force_login(user)

    response = client.get(reverse("plan_detail", args=[plan.pk]))

    assert response.status_code == 200
    assert plan_day.name.encode() in response.content
    assert plan_item.exercise.name.encode() in response.content
    assert b"Plan settings" in response.content


@pytest.mark.django_db
def test_plan_detail_hides_another_users_plan(client, other_user, plan):
    client.force_login(other_user)

    response = client.get(reverse("plan_detail", args=[plan.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_plan_detail_updates_settings(client, user, plan):
    client.force_login(user)

    response = client.post(
        reverse("plan_detail", args=[plan.pk]),
        {
            "name": "Renamed block",
            "split_type": Plan.SplitType.FULL_BODY,
            "start_date": "2026-11-09",
            "length_weeks": "",
        },
    )

    assert response.status_code == 302
    plan.refresh_from_db()
    assert plan.name == "Renamed block"
    assert plan.length_weeks is None


@pytest.mark.django_db
def test_plan_day_add_creates_a_day(client, user, plan, muscles):
    client.force_login(user)

    response = client.post(
        reverse("plan_day_add", args=[plan.pk]),
        {
            "name": "Day B – Upper",
            "weekday": Weekday.TUESDAY,
            "focus_muscles": [muscles["Chest"].pk, muscles["Back"].pk],
        },
    )

    assert response.status_code == 302
    day = plan.days.get()
    assert response.url == (reverse("plan_detail", args=[plan.pk]) + f"#day-{day.pk}")
    assert day.name == "Day B – Upper"
    assert day.weekday == Weekday.TUESDAY


@pytest.mark.django_db
def test_plan_day_add_rejects_a_duplicate_weekday(client, user, plan, plan_day):
    client.force_login(user)

    response = client.post(
        reverse("plan_day_add", args=[plan.pk]),
        {"name": "Another Monday", "weekday": Weekday.MONDAY},
    )

    assert response.status_code == 200
    assert b"That weekday already has a day" in response.content
    assert plan.days.count() == 1


@pytest.mark.django_db
def test_plan_day_edit_changes_the_name(client, user, plan, plan_day):
    client.force_login(user)

    response = client.post(
        reverse("plan_day_edit", args=[plan.pk, plan_day.pk]),
        {"name": "Lower strength", "weekday": Weekday.WEDNESDAY},
    )

    assert response.status_code == 302
    assert response.url == (reverse("plan_detail", args=[plan.pk]) + f"#day-{plan_day.pk}")
    plan_day.refresh_from_db()
    assert plan_day.name == "Lower strength"
    assert plan_day.weekday == Weekday.WEDNESDAY


@pytest.mark.django_db
def test_plan_day_delete_shows_a_confirmation_first(client, user, plan, plan_day):
    client.force_login(user)

    response = client.post(reverse("plan_day_delete", args=[plan.pk, plan_day.pk]))

    assert response.status_code == 200
    assert b"Delete day?" in response.content
    assert PlanDay.objects.filter(pk=plan_day.pk).exists()


@pytest.mark.django_db
def test_plan_day_delete_with_confirm_removes_the_day(client, user, plan, plan_day):
    client.force_login(user)

    response = client.post(
        reverse("plan_day_delete", args=[plan.pk, plan_day.pk]),
        {"confirm": "1"},
    )

    assert response.status_code == 302
    assert not PlanDay.objects.filter(pk=plan_day.pk).exists()


@pytest.mark.django_db
def test_plan_day_delete_reports_blocking_workouts(client, user, plan, plan_day):
    ScheduledWorkout.objects.create(
        user=user,
        plan=plan,
        plan_day=plan_day,
        scheduled_date=date(2026, 11, 2),
    )
    client.force_login(user)

    response = client.post(
        reverse("plan_day_delete", args=[plan.pk, plan_day.pk]),
        {"confirm": "1"},
        follow=True,
    )

    assert response.status_code == 200
    assert b"past or completed workouts" in response.content
    assert PlanDay.objects.filter(pk=plan_day.pk).exists()


@pytest.mark.django_db
def test_plan_item_new_renders_the_picker(client, user, plan, plan_day, seeded_exercise):
    client.force_login(user)

    response = client.get(reverse("plan_item_new", args=[plan.pk, plan_day.pk]))

    assert response.status_code == 200
    assert seeded_exercise.name.encode() in response.content
    assert b"Exercise picker" in response.content


@pytest.mark.django_db
def test_plan_item_new_creates_an_item(client, user, plan, plan_day, seeded_exercise):
    client.force_login(user)

    response = client.post(
        reverse("plan_item_new", args=[plan.pk, plan_day.pk]),
        {
            "exercise": seeded_exercise.pk,
            "target_sets": 4,
            "rep_min": 6,
            "rep_max": 8,
            "rest_seconds": 120,
            "notes": "Pause at the chest",
        },
    )

    assert response.status_code == 302
    assert response.url == (reverse("plan_detail", args=[plan.pk]) + f"#day-items-{plan_day.pk}")
    item = plan_day.items.get()
    assert item.exercise == seeded_exercise
    assert item.target_summary == "4 × 6–8"
    assert item.notes == "Pause at the chest"


@pytest.mark.django_db
def test_plan_item_new_rejects_a_missing_rep_range(client, user, plan, plan_day, seeded_exercise):
    client.force_login(user)

    response = client.post(
        reverse("plan_item_new", args=[plan.pk, plan_day.pk]),
        {
            "exercise": seeded_exercise.pk,
            "target_sets": 3,
            "rep_min": "",
            "rep_max": "",
            "rest_seconds": 90,
        },
    )

    assert response.status_code == 200
    assert b"Enter the low end of the rep range" in response.content
    assert plan_day.items.count() == 0


@pytest.mark.django_db
def test_plan_item_new_can_create_an_exercise_inline(client, user, plan, plan_day, muscles):
    client.force_login(user)

    response = client.post(
        reverse("plan_item_new", args=[plan.pk, plan_day.pk]),
        {
            "form_name": "exercise",
            "name": "Landmine Press",
            "primary_muscle": muscles["Shoulders"].pk,
            "tracking_type": Exercise.TrackingType.WEIGHT_REPS,
            "notes": "",
        },
    )

    exercise = Exercise.objects.get(user=user, name="Landmine Press")
    assert response.status_code == 302
    assert response.url == (
        reverse("plan_item_new", args=[plan.pk, plan_day.pk]) + f"?exercise={exercise.pk}"
    )


@pytest.mark.django_db
def test_plan_item_edit_updates_targets(client, user, plan, plan_item):
    client.force_login(user)

    response = client.post(
        reverse("plan_item_edit", args=[plan.pk, plan_item.pk]),
        {
            "exercise": plan_item.exercise.pk,
            "target_sets": 5,
            "rep_min": 5,
            "rep_max": 5,
            "rest_seconds": 180,
            "notes": "",
        },
    )

    assert response.status_code == 302
    assert response.url == (
        reverse("plan_detail", args=[plan.pk]) + f"#day-items-{plan_item.plan_day_id}"
    )
    plan_item.refresh_from_db()
    assert plan_item.target_summary == "5 × 5"
    assert plan_item.rest_seconds == 180


@pytest.mark.django_db
def test_plan_item_edit_rejects_another_users_item(client, other_user, plan, plan_item):
    client.force_login(other_user)

    response = client.post(
        reverse("plan_item_edit", args=[plan.pk, plan_item.pk]),
        {"exercise": plan_item.exercise.pk, "target_sets": 3, "rest_seconds": 90},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_plan_item_delete_shows_a_confirmation_first(client, user, plan, plan_item):
    client.force_login(user)

    response = client.post(reverse("plan_item_delete", args=[plan.pk, plan_item.pk]))

    assert response.status_code == 200
    assert b"Delete exercise?" in response.content
    assert PlanItem.objects.filter(pk=plan_item.pk).exists()


@pytest.mark.django_db
def test_plan_item_delete_with_confirm_removes_the_item(client, user, plan, plan_item):
    client.force_login(user)

    response = client.post(
        reverse("plan_item_delete", args=[plan.pk, plan_item.pk]),
        {"confirm": "1"},
    )

    assert response.status_code == 302
    assert response.url == (
        reverse("plan_detail", args=[plan.pk]) + f"#day-items-{plan_item.plan_day_id}"
    )
    assert not PlanItem.objects.filter(pk=plan_item.pk).exists()


@pytest.mark.django_db
def test_plan_item_move_swaps_order(client, user, plan, plan_day, plan_item, muscles):
    second_exercise = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    second = PlanItem.objects.create(
        plan_day=plan_day,
        exercise=second_exercise,
        order=1,
        target_sets=3,
        rep_min=8,
        rep_max=10,
    )
    client.force_login(user)

    response = client.post(
        reverse("plan_item_move", args=[plan.pk, second.pk]),
        {"direction": "up"},
    )

    assert response.status_code == 302
    assert response.url == (reverse("plan_detail", args=[plan.pk]) + f"#day-items-{plan_day.pk}")
    plan_item.refresh_from_db()
    second.refresh_from_db()
    assert second.order == 0
    assert plan_item.order == 1


@pytest.mark.django_db
def test_plan_day_reorder_saves_the_submitted_order(
    client, user, plan, plan_day, plan_item, muscles
):
    second_exercise = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    second = PlanItem.objects.create(
        plan_day=plan_day,
        exercise=second_exercise,
        order=1,
        target_sets=3,
        rep_min=8,
        rep_max=10,
    )
    client.force_login(user)

    response = client.post(
        reverse("plan_day_reorder", args=[plan.pk, plan_day.pk]),
        {"ordered_ids": f"{second.pk},{plan_item.pk}"},
    )

    assert response.status_code == 302
    assert response.url == (reverse("plan_detail", args=[plan.pk]) + f"#day-items-{plan_day.pk}")
    plan_item.refresh_from_db()
    second.refresh_from_db()
    assert second.order == 0
    assert plan_item.order == 1


@pytest.mark.django_db
def test_plan_day_superset_groups_items(client, user, plan, plan_day, plan_item, muscles):
    second_exercise = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    second = PlanItem.objects.create(
        plan_day=plan_day,
        exercise=second_exercise,
        order=1,
        target_sets=3,
        rep_min=8,
        rep_max=10,
    )
    client.force_login(user)

    response = client.post(
        reverse("plan_day_superset", args=[plan.pk, plan_day.pk]),
        {"item_ids": [plan_item.pk, second.pk]},
    )

    assert response.status_code == 302
    assert response.url == (reverse("plan_detail", args=[plan.pk]) + f"#day-items-{plan_day.pk}")
    plan_item.refresh_from_db()
    second.refresh_from_db()
    assert plan_item.superset_group == "A"
    assert second.superset_group == "A"


@pytest.mark.django_db
def test_plan_day_superset_reports_a_non_consecutive_selection(
    client, user, plan, plan_day, plan_item, muscles
):
    middle_exercise = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    PlanItem.objects.create(
        plan_day=plan_day,
        exercise=middle_exercise,
        order=1,
        target_sets=3,
        rep_min=8,
        rep_max=10,
    )
    last_exercise = Exercise.objects.create(
        user=None,
        name="Cable Fly",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    last = PlanItem.objects.create(
        plan_day=plan_day,
        exercise=last_exercise,
        order=2,
        target_sets=3,
        rep_min=8,
        rep_max=10,
    )
    client.force_login(user)

    response = client.post(
        reverse("plan_day_superset", args=[plan.pk, plan_day.pk]),
        {"item_ids": [plan_item.pk, last.pk]},
        follow=True,
    )

    assert response.status_code == 200
    assert b"consecutive" in response.content


@pytest.mark.django_db
def test_plan_item_move_htmx_swaps_only_the_items_region(
    client, user, plan, plan_day, plan_item, muscles
):
    second = _second_plan_item(plan_day, muscles)
    client.force_login(user)

    response = client.post(
        reverse("plan_item_move", args=[plan.pk, second.pk]),
        {"direction": "up"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assertTemplateUsed(response, "plans/_day_items_swap.html")
    assertTemplateUsed(response, "plans/_day_items.html")
    assert b"<html" not in response.content
    assert f'id="day-items-{plan_day.pk}"'.encode() in response.content
    assert b'id="messages"' in response.content
    assert b'hx-swap-oob="true"' in response.content
    content = response.content.decode()
    assert content.index(second.exercise.name) < content.index(plan_item.exercise.name)

    plan_item.refresh_from_db()
    second.refresh_from_db()
    assert second.order == 0
    assert plan_item.order == 1


@pytest.mark.django_db
def test_plan_item_move_htmx_keeps_the_error_in_place(client, user, plan, plan_day, plan_item):
    client.force_login(user)

    response = client.post(
        reverse("plan_item_move", args=[plan.pk, plan_item.pk]),
        {"direction": "sideways"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assertTemplateUsed(response, "plans/_day_items_swap.html")
    assert b"Choose up or down." in response.content
    assert b'hx-swap-oob="true"' in response.content


@pytest.mark.django_db
def test_plan_day_reorder_htmx_swaps_the_items_region(
    client, user, plan, plan_day, plan_item, muscles
):
    second = _second_plan_item(plan_day, muscles)
    client.force_login(user)

    response = client.post(
        reverse("plan_day_reorder", args=[plan.pk, plan_day.pk]),
        {"ordered_ids": f"{second.pk},{plan_item.pk}"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assertTemplateUsed(response, "plans/_day_items_swap.html")
    assert b"Order saved." in response.content
    assert b'hx-swap-oob="true"' in response.content
    content = response.content.decode()
    assert content.index(second.exercise.name) < content.index(plan_item.exercise.name)

    plan_item.refresh_from_db()
    second.refresh_from_db()
    assert second.order == 0
    assert plan_item.order == 1


@pytest.mark.django_db
def test_plan_day_superset_htmx_swaps_the_items_region(
    client, user, plan, plan_day, plan_item, muscles
):
    second = _second_plan_item(plan_day, muscles)
    client.force_login(user)

    response = client.post(
        reverse("plan_day_superset", args=[plan.pk, plan_day.pk]),
        {"item_ids": [plan_item.pk, second.pk]},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assertTemplateUsed(response, "plans/_day_items_swap.html")
    assert b"Superset A created." in response.content
    assert b">A</span>" in response.content
    assert b'hx-swap-oob="true"' in response.content

    plan_item.refresh_from_db()
    second.refresh_from_db()
    assert plan_item.superset_group == "A"
    assert second.superset_group == "A"


@pytest.mark.django_db
def test_plan_day_superset_clear_htmx_swaps_the_items_region(
    client, user, plan, plan_day, plan_item, muscles
):
    second = _second_plan_item(plan_day, muscles)
    plan_item.superset_group = "A"
    plan_item.save(update_fields=["superset_group"])
    second.superset_group = "A"
    second.save(update_fields=["superset_group"])
    client.force_login(user)

    response = client.post(
        reverse("plan_day_superset_clear", args=[plan.pk, plan_day.pk]),
        {"group": "A"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assertTemplateUsed(response, "plans/_day_items_swap.html")
    assert b"Superset removed." in response.content
    assert b'hx-swap-oob="true"' in response.content

    plan_item.refresh_from_db()
    second.refresh_from_db()
    assert plan_item.superset_group == ""
    assert second.superset_group == ""


@pytest.mark.django_db
def test_plan_day_superset_htmx_reports_a_non_consecutive_selection(
    client, user, plan, plan_day, plan_item, muscles
):
    middle = _second_plan_item(plan_day, muscles)
    last = _second_plan_item(plan_day, muscles, name="Cable Fly", order=2)
    client.force_login(user)

    response = client.post(
        reverse("plan_day_superset", args=[plan.pk, plan_day.pk]),
        {"item_ids": [plan_item.pk, last.pk]},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assertTemplateUsed(response, "plans/_day_items_swap.html")
    assert b"consecutive" in response.content
    assert b'hx-swap-oob="true"' in response.content
    assert middle.superset_group == ""


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "payload"),
    [
        ("plan_item_move", {"direction": "up"}),
        ("plan_day_reorder", {"ordered_ids": ""}),
        ("plan_day_superset", {"item_ids": []}),
        ("plan_day_superset_clear", {"group": "A"}),
    ],
)
def test_plan_partial_actions_are_scoped_to_the_owner(
    client, other_user, plan, plan_day, plan_item, url_name, payload
):
    client.force_login(other_user)
    if url_name == "plan_item_move":
        url = reverse(url_name, args=[plan.pk, plan_item.pk])
    else:
        url = reverse(url_name, args=[plan.pk, plan_day.pk])

    response = client.post(url, payload, HTTP_HX_REQUEST="true")

    assert response.status_code == 404


@pytest.mark.django_db
def test_plan_activate_asks_before_archiving_the_current_plan(
    client, user, plan, plan_day, active_plan
):
    client.force_login(user)

    response = client.post(reverse("plan_activate", args=[plan.pk]))

    assert response.status_code == 200
    assert b"Activate plan?" in response.content
    plan.refresh_from_db()
    active_plan.refresh_from_db()
    assert plan.is_draft
    assert active_plan.is_active


@pytest.mark.django_db
def test_plan_activate_with_confirm_switches_the_active_plan(
    client, user, plan, plan_day, active_plan
):
    client.force_login(user)

    response = client.post(
        reverse("plan_activate", args=[plan.pk]),
        {"confirm": "1"},
    )

    assert response.status_code == 302
    plan.refresh_from_db()
    active_plan.refresh_from_db()
    assert plan.is_active
    assert active_plan.is_archived
    assert plan.scheduled_workouts.exists()


@pytest.mark.django_db
def test_plan_archive_shows_a_confirmation_first(client, user, plan):
    client.force_login(user)

    response = client.post(reverse("plan_archive", args=[plan.pk]))

    assert response.status_code == 200
    assert b"Archive plan?" in response.content
    plan.refresh_from_db()
    assert plan.is_draft


@pytest.mark.django_db
def test_plan_archive_with_confirm_archives(client, user, plan):
    client.force_login(user)

    response = client.post(
        reverse("plan_archive", args=[plan.pk]),
        {"confirm": "1"},
    )

    assert response.status_code == 302
    plan.refresh_from_db()
    assert plan.is_archived
    assert plan.archived_at is not None


@pytest.mark.django_db
def test_plan_duplicate_creates_a_draft(client, user, plan, plan_day, plan_item):
    client.force_login(user)

    response = client.post(reverse("plan_duplicate", args=[plan.pk]))

    copy = Plan.objects.get(user=user, name="Upper/Lower Block 3 (copy)")
    assert response.status_code == 302
    assert response.url == reverse("plan_detail", args=[copy.pk])
    assert copy.days.count() == 1
    assert copy.days.get().items.count() == 1


@pytest.mark.django_db
def test_plan_picker_returns_a_partial(client, user, plan, plan_day, seeded_exercise):
    client.force_login(user)

    response = client.get(
        reverse("plan_picker", args=[plan.pk]),
        {"day": plan_day.pk, "q": "bench"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert seeded_exercise.name.encode() in response.content
    assert b"<html" not in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_scheduled_mark_missed_marks_todays_workout(client, user, active_plan, active_plan_day):
    workout = ScheduledWorkout.objects.create(
        user=user,
        plan=active_plan,
        plan_day=active_plan_day,
        scheduled_date=TODAY,
    )
    client.force_login(user)

    response = client.post(reverse("scheduled_mark_missed", args=[workout.pk]))

    assert response.status_code == 302
    assert response.url == reverse("today")
    workout.refresh_from_db()
    assert workout.status == ScheduledWorkout.Status.MISSED
    assert workout.marked_missed_manually is True
