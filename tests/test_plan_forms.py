from decimal import Decimal

import pytest

from apps.exercises.models import Exercise
from apps.plans.forms import PlanDayForm, PlanForm, PlanItemForm
from apps.plans.models import Plan, PlanItem, Weekday


@pytest.mark.django_db
def test_plan_form_rejects_a_zero_length():
    form = PlanForm(
        data={
            "name": "Block",
            "split_type": Plan.SplitType.CUSTOM,
            "start_date": "2026-11-09",
            "length_weeks": 0,
        }
    )

    assert not form.is_valid()
    assert "length_weeks" in form.errors


@pytest.mark.django_db
def test_plan_form_allows_a_blank_length():
    form = PlanForm(
        data={
            "name": "Block",
            "split_type": Plan.SplitType.CUSTOM,
            "start_date": "2026-11-09",
            "length_weeks": "",
        }
    )

    assert form.is_valid()
    assert form.cleaned_data["length_weeks"] is None


@pytest.mark.django_db
def test_plan_day_form_rejects_a_weekday_clash(plan, plan_day):
    form = PlanDayForm(
        data={"name": "Another Monday", "weekday": Weekday.MONDAY},
        plan=plan,
    )

    assert not form.is_valid()
    assert "weekday" in form.errors


@pytest.mark.django_db
def test_plan_day_form_allows_editing_the_same_day(plan, plan_day):
    form = PlanDayForm(
        data={"name": "Renamed", "weekday": Weekday.MONDAY},
        instance=plan_day,
        plan=plan,
    )

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_plan_item_form_defaults_rest_from_user_settings(user, plan_day, seeded_exercise):
    user.settings.default_rest_seconds = 150
    user.settings.save(update_fields=["default_rest_seconds"])

    form = PlanItemForm(user=user, day=plan_day)

    assert form.initial["rest_seconds"] == 150
    assert form.initial["target_sets"] == 3


@pytest.mark.django_db
def test_plan_item_form_reports_target_errors(plan_day, user, seeded_exercise):
    form = PlanItemForm(
        data={
            "exercise": seeded_exercise.pk,
            "target_sets": 3,
            "rep_min": 12,
            "rep_max": 8,
            "rest_seconds": 90,
        },
        user=user,
        day=plan_day,
    )

    assert not form.is_valid()
    assert "Max reps must be at least min reps" in form.errors["rep_max"][0]


@pytest.mark.django_db
def test_plan_item_form_tracking_comes_from_the_selected_exercise(user, plan_day, seeded_exercise):
    form = PlanItemForm(
        data={
            "exercise": seeded_exercise.pk,
            "target_sets": 3,
            "rep_min": 8,
            "rep_max": 10,
            "rest_seconds": 90,
        },
        user=user,
        day=plan_day,
    )

    assert form.selected_tracking == Exercise.TrackingType.WEIGHT_REPS


@pytest.mark.django_db
def test_plan_item_form_excludes_archived_exercises(user, plan_day, muscles):
    archived = Exercise.objects.create(
        user=user,
        name="Old movement",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
        is_archived=True,
    )

    form = PlanItemForm(user=user, day=plan_day)

    assert archived not in form.fields["exercise"].queryset


@pytest.mark.django_db
def test_exercise_select_adds_the_tracking_type(user, plan_day, seeded_exercise):
    form = PlanItemForm(
        initial={"exercise": seeded_exercise.pk},
        user=user,
        day=plan_day,
    )

    html = str(form["exercise"])

    assert f'data-tracking="{Exercise.TrackingType.WEIGHT_REPS}"' in html
    assert 'data-unit="MI"' in html


@pytest.mark.django_db
def test_plan_item_form_converts_distance_from_the_override_unit(user, plan_day, muscles):
    sled = Exercise.objects.create(
        user=None,
        name="Sled Push",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.DISTANCE,
        default_distance_unit="YD",
    )
    form = PlanItemForm(
        data={
            "exercise": sled.pk,
            "target_sets": 4,
            "target_distance": "15",
            "distance_unit": "YD",
            "rest_seconds": 90,
        },
        user=user,
        day=plan_day,
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["target_distance_m"] == Decimal("13.7160")
    assert form.cleaned_data["distance_unit"] == "YD"


@pytest.mark.django_db
def test_plan_item_form_uses_the_exercise_default_unit(user, plan_day, muscles):
    sled = Exercise.objects.create(
        user=None,
        name="Sled Push",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.DISTANCE,
        default_distance_unit="YD",
    )
    form = PlanItemForm(
        data={
            "exercise": sled.pk,
            "target_sets": 4,
            "target_distance": "15",
            "distance_unit": "",
            "rest_seconds": 90,
        },
        user=user,
        day=plan_day,
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["target_distance_m"] == Decimal("13.7160")
    assert form.cleaned_data["distance_unit"] == "YD"


@pytest.mark.django_db
def test_plan_item_form_edit_shows_distance_in_the_snapshotted_unit(user, plan_day, muscles):
    sled = Exercise.objects.create(
        user=None,
        name="Sled Push",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.DISTANCE,
        default_distance_unit="YD",
    )
    item = PlanItem.objects.create(
        plan_day=plan_day,
        exercise=sled,
        target_sets=3,
        target_distance_m=Decimal("13.7160"),
        distance_unit="YD",
    )

    form = PlanItemForm(instance=item, user=user, day=plan_day)

    assert form.initial["target_distance"] == "15"
    assert form.initial["distance_unit"] == "YD"


@pytest.mark.django_db
def test_plan_item_form_cleans_cardio_targets(user, plan_day, muscles):
    cardio = Exercise.objects.create(
        user=None,
        name="Treadmill Run",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.CARDIO,
    )
    form = PlanItemForm(
        data={
            "exercise": cardio.pk,
            "target_sets": 4,
            "target_seconds": 1800,
            "rest_seconds": 0,
        },
        user=user,
        day=plan_day,
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["target_sets"] == 1
    assert form.cleaned_data["rep_min"] is None


@pytest.mark.django_db
def test_plan_item_form_edit_keeps_the_existing_order(plan_item, user):
    form = PlanItemForm(instance=plan_item, user=user, day=plan_item.plan_day)

    assert PlanItem.objects.get(pk=plan_item.pk).order == 0
    assert form.instance.pk == plan_item.pk
