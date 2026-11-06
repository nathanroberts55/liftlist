from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.exercises.models import Exercise, MuscleGroup
from apps.plans.models import Plan, PlanDay, PlanItem, Weekday
from apps.plans.services.plans import (
    add_day,
    add_item,
    clean_item_targets,
    clear_superset,
    create_plan,
    create_superset,
    delete_day,
    delete_item,
    duplicate_plan,
    get_plan,
    get_plan_day,
    get_plan_item,
    list_plans,
    move_item,
    picker_exercises,
    reorder_items,
    update_day,
    update_item,
    update_plan,
    weekday_labels,
)

TODAY = date(2026, 11, 9)


# --- Plans ------------------------------------------------------------------


@pytest.mark.django_db
def test_create_plan_trims_the_name(user):
    plan = create_plan(
        user,
        name="  Upper/Lower  ",
        split_type=Plan.SplitType.UPPER_LOWER,
        start_date=TODAY,
    )

    assert plan.name == "Upper/Lower"
    assert plan.is_draft
    assert plan.user == user


@pytest.mark.django_db
def test_create_plan_rejects_a_blank_name(user):
    with pytest.raises(ValidationError):
        create_plan(user, name="  ", split_type=Plan.SplitType.CUSTOM, start_date=TODAY)


@pytest.mark.django_db
def test_create_plan_rejects_a_zero_length(user):
    with pytest.raises(ValidationError):
        create_plan(
            user,
            name="Zero",
            split_type=Plan.SplitType.CUSTOM,
            start_date=TODAY,
            length_weeks=0,
        )


@pytest.mark.django_db
def test_list_plans_groups_statuses(user, plan):
    active = Plan.objects.create(
        user=user,
        name="Active",
        start_date=TODAY,
        status=Plan.Status.ACTIVE,
    )
    archived = Plan.objects.create(
        user=user,
        name="Archived",
        start_date=TODAY,
        status=Plan.Status.ARCHIVED,
    )

    groups = list_plans(user)

    assert groups["active"] == [active]
    assert groups["drafts"] == [plan]
    assert groups["archived"] == [archived]


@pytest.mark.django_db
def test_get_plan_hides_other_users_plans(user, other_user, plan):
    from django.http import Http404

    with pytest.raises(Http404):
        get_plan(other_user, plan.pk)


@pytest.mark.django_db
def test_update_plan_changes_settings(user, plan):
    updated = update_plan(
        user,
        plan,
        name="New name",
        split_type=Plan.SplitType.PPL,
        start_date=date(2026, 12, 1),
        length_weeks=None,
    )

    assert updated.name == "New name"
    assert updated.split_type == Plan.SplitType.PPL
    assert updated.length_weeks is None


@pytest.mark.django_db
def test_update_plan_rejects_another_users_plan(other_user, plan):
    with pytest.raises(PermissionDenied):
        update_plan(
            other_user,
            plan,
            name="Hijack",
            split_type=Plan.SplitType.CUSTOM,
            start_date=TODAY,
        )


@pytest.mark.django_db
def test_duplicate_plan_copies_days_and_items(user, plan, plan_day, plan_item, muscles):
    plan_day.focus_muscles.set([muscles["Chest"]])

    copy = duplicate_plan(user, plan)

    assert copy.pk != plan.pk
    assert copy.name == "Upper/Lower Block 3 (copy)"
    assert copy.is_draft
    copied_day = copy.days.get()
    assert copied_day.name == plan_day.name
    assert list(copied_day.focus_muscles.all()) == [muscles["Chest"]]
    copied_item = copied_day.items.get()
    assert copied_item.exercise == plan_item.exercise
    assert copied_item.target_summary == plan_item.target_summary


@pytest.mark.django_db
def test_duplicate_plan_makes_names_unique(user, plan):
    duplicate_plan(user, plan)
    second = duplicate_plan(user, plan)

    assert second.name == "Upper/Lower Block 3 (copy) 2"


# --- Days -------------------------------------------------------------------


@pytest.mark.django_db
def test_add_day_sets_order_and_focus(user, plan, muscles):
    day = add_day(
        user,
        plan,
        name="Day B – Upper",
        weekday=Weekday.TUESDAY,
        focus_muscle_ids=[muscles["Chest"].pk, muscles["Biceps"].pk],
    )

    assert day.order == Weekday.TUESDAY
    assert set(day.focus_muscles.values_list("name", flat=True)) == {"Chest", "Biceps"}


@pytest.mark.django_db
def test_add_day_rejects_a_duplicate_weekday(user, plan, plan_day):
    with pytest.raises(ValidationError):
        add_day(user, plan, name="Another Monday", weekday=Weekday.MONDAY)


@pytest.mark.django_db
def test_add_day_rejects_unknown_focus_muscles(user, plan):
    with pytest.raises(ValidationError):
        add_day(
            user,
            plan,
            name="Bad focus",
            weekday=Weekday.TUESDAY,
            focus_muscle_ids=[999999],
        )


@pytest.mark.django_db
def test_update_day_moves_weekday(user, plan, plan_day):
    updated = update_day(
        user,
        plan_day,
        name="Day A",
        weekday=Weekday.WEDNESDAY,
    )

    assert updated.weekday == Weekday.WEDNESDAY
    assert updated.order == Weekday.WEDNESDAY


@pytest.mark.django_db
def test_update_day_rejects_a_clash(user, plan, plan_day):
    PlanDay.objects.create(plan=plan, name="Tuesday", weekday=Weekday.TUESDAY)

    with pytest.raises(ValidationError):
        update_day(user, plan_day, name="Monday", weekday=Weekday.TUESDAY)


@pytest.mark.django_db
def test_delete_day_removes_its_items(user, plan, plan_day, plan_item):
    delete_day(user, plan_day)

    assert not PlanDay.objects.filter(pk=plan_day.pk).exists()
    assert not PlanItem.objects.filter(pk=plan_item.pk).exists()


@pytest.mark.django_db
def test_delete_day_is_blocked_by_past_workouts(user, plan, plan_day):
    from apps.plans.models import ScheduledWorkout

    ScheduledWorkout.objects.create(
        user=user,
        plan=plan,
        plan_day=plan_day,
        scheduled_date=date(2026, 11, 2),
    )

    with pytest.raises(ValidationError):
        delete_day(user, plan_day, today=TODAY)


@pytest.mark.django_db
def test_delete_day_is_blocked_by_completed_workouts(user, plan, plan_day):
    from apps.plans.models import ScheduledWorkout

    ScheduledWorkout.objects.create(
        user=user,
        plan=plan,
        plan_day=plan_day,
        scheduled_date=TODAY,
        status=ScheduledWorkout.Status.COMPLETED,
    )

    with pytest.raises(ValidationError):
        delete_day(user, plan_day, today=TODAY)


@pytest.mark.django_db
def test_get_plan_day_and_item_are_scoped(user, other_user, plan, plan_day, plan_item):
    from django.http import Http404

    assert get_plan_day(user, plan.pk, plan_day.pk) == plan_day
    assert get_plan_item(user, plan.pk, plan_item.pk) == plan_item

    with pytest.raises(Http404):
        get_plan_day(other_user, plan.pk, plan_day.pk)
    with pytest.raises(Http404):
        get_plan_item(other_user, plan.pk, plan_item.pk)


# --- Items ------------------------------------------------------------------


@pytest.mark.django_db
def test_add_item_appends_in_order(user, plan_day, seeded_exercise, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )

    first = add_item(
        user,
        plan_day,
        exercise=seeded_exercise,
        target_sets=4,
        rep_min=6,
        rep_max=8,
        rest_seconds=120,
    )
    later = add_item(
        user,
        plan_day,
        exercise=second,
        target_sets=3,
        rep_min=8,
        rep_max=10,
        rest_seconds=90,
    )

    assert first.order == 0
    assert later.order == 1


@pytest.mark.django_db
def test_add_item_rejects_another_users_custom_exercise(user, other_user, plan_day):
    private = Exercise.objects.create(
        user=other_user,
        name="Private movement",
        primary_muscle=MuscleGroup.objects.get(name="Chest"),
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )

    with pytest.raises(ValidationError):
        add_item(
            user,
            plan_day,
            exercise=private,
            target_sets=3,
            rep_min=8,
            rep_max=10,
        )


@pytest.mark.django_db
def test_update_item_changes_targets(user, plan_item):
    updated = update_item(
        user,
        plan_item,
        exercise=plan_item.exercise,
        target_sets=5,
        rep_min=5,
        rep_max=5,
        rest_seconds=180,
        notes="  Brace hard  ",
    )

    assert updated.target_sets == 5
    assert updated.notes == "Brace hard"
    assert updated.target_summary == "5 × 5"


@pytest.mark.django_db
def test_delete_item_renumbers_the_day(user, plan_day, seeded_exercise, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    first = add_item(user, plan_day, exercise=seeded_exercise, rep_min=8, rep_max=10)
    later = add_item(user, plan_day, exercise=second, rep_min=8, rep_max=10)

    delete_item(user, first)

    later.refresh_from_db()
    assert later.order == 0


@pytest.mark.django_db
def test_clean_item_targets_weight_reps_normalizes(user, seeded_exercise):
    cleaned = clean_item_targets(
        seeded_exercise,
        target_sets="4",
        rep_min="6",
        rep_max="8",
        target_seconds="60",
        target_distance_mi="3.5",
        rest_seconds="120",
    )

    assert cleaned == {
        "target_sets": 4,
        "rep_min": 6,
        "rep_max": 8,
        "target_seconds": None,
        "target_distance_mi": None,
        "rest_seconds": 120,
    }


@pytest.mark.django_db
def test_clean_item_targets_requires_both_reps(user, seeded_exercise):
    with pytest.raises(ValidationError) as error:
        clean_item_targets(seeded_exercise, rep_min=8, rep_max=None)

    assert "rep_max" in error.value.message_dict


@pytest.mark.django_db
def test_clean_item_targets_rejects_reversed_reps(user, seeded_exercise):
    with pytest.raises(ValidationError) as error:
        clean_item_targets(seeded_exercise, rep_min=10, rep_max=8)

    assert "rep_max" in error.value.message_dict


@pytest.mark.django_db
def test_clean_item_targets_timed_requires_seconds(user, seeded_exercise):
    seeded_exercise.tracking_type = Exercise.TrackingType.TIMED
    seeded_exercise.save()

    with pytest.raises(ValidationError) as error:
        clean_item_targets(seeded_exercise)

    assert "target_seconds" in error.value.message_dict


@pytest.mark.django_db
def test_clean_item_targets_cardio_forces_one_set(user, seeded_exercise):
    seeded_exercise.tracking_type = Exercise.TrackingType.CARDIO
    seeded_exercise.save()

    cleaned = clean_item_targets(
        seeded_exercise,
        target_sets=5,
        target_distance_mi="2.5",
        rest_seconds=0,
    )

    assert cleaned["target_sets"] == 1
    assert cleaned["rep_min"] is None
    assert cleaned["target_distance_mi"] == 2.5


@pytest.mark.django_db
def test_clean_item_targets_cardio_requires_duration_or_distance(user, seeded_exercise):
    seeded_exercise.tracking_type = Exercise.TrackingType.CARDIO
    seeded_exercise.save()

    with pytest.raises(ValidationError) as error:
        clean_item_targets(seeded_exercise)

    assert "target_seconds" in error.value.message_dict


# --- Ordering and supersets -------------------------------------------------


def _item_at(day, exercise, order, **kwargs):
    return PlanItem.objects.create(
        plan_day=day,
        exercise=exercise,
        order=order,
        target_sets=kwargs.pop("target_sets", 3),
        rep_min=kwargs.pop("rep_min", 8),
        rep_max=kwargs.pop("rep_max", 10),
        **kwargs,
    )


@pytest.mark.django_db
def test_move_item_swaps_neighbours(user, plan_day, seeded_exercise, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    first = _item_at(plan_day, seeded_exercise, 0)
    later = _item_at(plan_day, second, 1)

    move_item(user, later, "up")

    first.refresh_from_db()
    later.refresh_from_db()
    assert later.order == 0
    assert first.order == 1


@pytest.mark.django_db
def test_move_item_does_nothing_at_the_edge(user, plan_item):
    move_item(user, plan_item, "up")

    plan_item.refresh_from_db()
    assert plan_item.order == 0


@pytest.mark.django_db
def test_move_item_moves_a_whole_superset_block(user, plan_day, seeded_exercise, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    third = Exercise.objects.create(
        user=None,
        name="Cable Fly",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    lead = _item_at(plan_day, third, 0)
    group_a = _item_at(plan_day, seeded_exercise, 1, superset_group="A")
    group_b = _item_at(plan_day, second, 2, superset_group="A")

    move_item(user, group_b, "up")

    lead.refresh_from_db()
    group_a.refresh_from_db()
    group_b.refresh_from_db()
    assert [lead.order, group_a.order, group_b.order] == [2, 0, 1]


@pytest.mark.django_db
def test_create_superset_groups_consecutive_items(user, plan_day, seeded_exercise, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    first = _item_at(plan_day, seeded_exercise, 0)
    later = _item_at(plan_day, second, 1)

    label = create_superset(user, plan_day, [first.pk, later.pk])

    first.refresh_from_db()
    later.refresh_from_db()
    assert label == "A"
    assert first.superset_group == "A"
    assert later.superset_group == "A"


@pytest.mark.django_db
def test_create_superset_uses_the_next_free_label(user, plan_day, seeded_exercise, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    third = Exercise.objects.create(
        user=None,
        name="Cable Fly",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    fourth = Exercise.objects.create(
        user=None,
        name="Face Pull",
        primary_muscle=muscles["Shoulders"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    _item_at(plan_day, seeded_exercise, 0, superset_group="A")
    _item_at(plan_day, second, 1, superset_group="A")
    third_item = _item_at(plan_day, third, 2)
    fourth_item = _item_at(plan_day, fourth, 3)

    label = create_superset(user, plan_day, [third_item.pk, fourth_item.pk])

    assert label == "B"


@pytest.mark.django_db
def test_create_superset_rejects_non_consecutive_items(user, plan_day, seeded_exercise, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    third = Exercise.objects.create(
        user=None,
        name="Cable Fly",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    first = _item_at(plan_day, seeded_exercise, 0)
    _item_at(plan_day, second, 1)
    last = _item_at(plan_day, third, 2)

    with pytest.raises(ValidationError):
        create_superset(user, plan_day, [first.pk, last.pk])


@pytest.mark.django_db
def test_create_superset_requires_two_items(user, plan_day, plan_item):
    with pytest.raises(ValidationError):
        create_superset(user, plan_day, [plan_item.pk])


@pytest.mark.django_db
def test_clear_superset_clears_the_group(user, plan_day, plan_item):
    plan_item.superset_group = "A"
    plan_item.save(update_fields=["superset_group"])
    second = _item_at(
        plan_day,
        plan_item.exercise,
        1,
        superset_group="A",
    )

    clear_superset(user, plan_day, "A")

    plan_item.refresh_from_db()
    second.refresh_from_db()
    assert plan_item.superset_group == ""
    assert second.superset_group == ""


@pytest.mark.django_db
def test_clear_superset_rejects_an_unknown_label(user, plan_day):
    with pytest.raises(ValidationError):
        clear_superset(user, plan_day, "1")


@pytest.mark.django_db
def test_delete_item_clears_a_lonely_superset_label(user, plan_day, plan_item, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    plan_item.superset_group = "A"
    plan_item.save(update_fields=["superset_group"])
    survivor = _item_at(plan_day, second, 1, superset_group="A")

    delete_item(user, plan_item)

    survivor.refresh_from_db()
    assert survivor.superset_group == ""


@pytest.mark.django_db
def test_reorder_items_persists_a_new_order(user, plan_day, seeded_exercise, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    first = _item_at(plan_day, seeded_exercise, 0)
    later = _item_at(plan_day, second, 1)

    reorder_items(user, plan_day, [later.pk, first.pk])

    first.refresh_from_db()
    later.refresh_from_db()
    assert [later.order, first.order] == [0, 1]


@pytest.mark.django_db
def test_reorder_items_rejects_a_missing_id(user, plan_day, plan_item):
    with pytest.raises(ValidationError):
        reorder_items(user, plan_day, [plan_item.pk, 999999])


@pytest.mark.django_db
def test_reorder_items_rejects_splitting_a_superset(user, plan_day, seeded_exercise, muscles):
    second = Exercise.objects.create(
        user=None,
        name="Barbell Row",
        primary_muscle=muscles["Back"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    third = Exercise.objects.create(
        user=None,
        name="Cable Fly",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    first = _item_at(plan_day, seeded_exercise, 0, superset_group="A")
    second_item = _item_at(plan_day, second, 1, superset_group="A")
    third_item = _item_at(plan_day, third, 2)

    with pytest.raises(ValidationError):
        reorder_items(user, plan_day, [first.pk, third_item.pk, second_item.pk])


# --- Picker and labels ------------------------------------------------------


@pytest.mark.django_db
def test_picker_puts_focus_muscles_first(user, plan_day, muscles, seeded_exercise):
    Exercise.objects.create(
        user=None,
        name="Leg Press",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    plan_day.focus_muscles.set([muscles["Quads"]])

    groups = picker_exercises(user, plan_day)

    assert groups[0]["muscle"] == muscles["Quads"]
    assert groups[0]["is_focus"] is True


@pytest.mark.django_db
def test_picker_filters_by_name(user, plan_day, seeded_exercise):
    groups = picker_exercises(user, plan_day, query="bench")

    assert [exercise.name for group in groups for exercise in group["exercises"]] == [
        "Barbell Bench Press"
    ]


@pytest.mark.django_db
def test_weekday_labels_use_short_letters(user, plan, plan_day):
    PlanDay.objects.create(plan=plan, name="Day B", weekday=Weekday.THURSDAY)
    PlanDay.objects.create(plan=plan, name="Day C", weekday=Weekday.FRIDAY)

    assert weekday_labels(plan) == "M Th F"
