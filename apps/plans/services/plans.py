"""Plan builder services (F-03).

Views parse input and call these functions. Everything that decides ownership,
validation, ordering, or when the schedule must be regenerated lives here.
"""

from collections import Counter
from itertools import groupby

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.exercises.models import Exercise, MuscleGroup

from ..models import Plan, PlanDay, PlanItem
from . import scheduling

SUPERSET_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# --- Reads ------------------------------------------------------------------


def list_plans(user) -> dict:
    """Group a user's plans for the plan list screen."""
    plans = Plan.objects.for_user(user).prefetch_related("days").order_by("-updated_at", "name")
    grouped = {
        "active": [],
        "drafts": [],
        "archived": [],
    }
    for plan in plans:
        if plan.is_active:
            grouped["active"].append(plan)
        elif plan.is_draft:
            grouped["drafts"].append(plan)
        else:
            grouped["archived"].append(plan)
    return grouped


def get_plan(user, plan_id) -> Plan:
    return get_object_or_404(Plan.objects.for_user(user), pk=plan_id)


def get_plan_day(user, plan_id, day_id) -> PlanDay:
    plan = get_plan(user, plan_id)
    return get_object_or_404(plan.days.all(), pk=day_id)


def get_plan_item(user, plan_id, item_id) -> PlanItem:
    plan = get_plan(user, plan_id)
    return get_object_or_404(
        PlanItem.objects.filter(plan_day__plan=plan).select_related(
            "exercise", "plan_day", "plan_day__plan"
        ),
        pk=item_id,
    )


def picker_exercises(user, day, query: str = "", usage_counts=None) -> list[dict]:
    """Visible exercises grouped muscle-by-muscle, focus groups first.

    ``usage_counts`` maps exercise ids to how often the user has done them.
    Workout sessions arrive in M3; until then callers get alphabetical order.
    """
    focus_ids = set(day.focus_muscles.values_list("id", flat=True))
    queryset = (
        Exercise.objects.visible_to(user)
        .select_related("primary_muscle")
        .prefetch_related("secondary_muscles")
    )
    if query:
        queryset = queryset.filter(name__icontains=query.strip())

    usage = usage_counts or {}
    exercises = sorted(
        queryset,
        key=lambda exercise: (
            0 if exercise.primary_muscle_id in focus_ids else 1,
            -usage.get(exercise.pk, 0),
            exercise.primary_muscle.display_order,
            exercise.name.lower(),
        ),
    )
    groups = []
    for muscle, items in groupby(exercises, key=lambda exercise: exercise.primary_muscle):
        groups.append(
            {
                "muscle": muscle,
                "is_focus": muscle.pk in focus_ids,
                "exercises": list(items),
            }
        )
    return groups


# --- Plan CRUD --------------------------------------------------------------


def _ensure_owner(user, plan: Plan) -> None:
    if plan.user_id != user.pk:
        raise PermissionDenied("You can only change your own plans.")


def _today_or_now(today):
    return today if today is not None else timezone.localdate()


def _clean_name(value: str, *, field: str = "name") -> str:
    name = (value or "").strip()
    if not name:
        raise ValidationError({field: "Enter a name."})
    return name


@transaction.atomic
def create_plan(user, *, name: str, split_type: str, start_date, length_weeks=None) -> Plan:
    """Create a draft plan."""
    plan = Plan(
        user=user,
        name=_clean_name(name),
        split_type=split_type,
        start_date=start_date,
        length_weeks=length_weeks,
    )
    plan.full_clean()
    plan.save()
    return plan


@transaction.atomic
def update_plan(
    user,
    plan: Plan,
    *,
    name: str,
    split_type: str,
    start_date,
    length_weeks=None,
    today=None,
) -> Plan:
    """Update plan settings. Active plans refresh their future schedule."""
    _ensure_owner(user, plan)
    plan.name = _clean_name(name)
    plan.split_type = split_type
    plan.start_date = start_date
    plan.length_weeks = length_weeks
    plan.full_clean()
    plan.save()
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))
    return plan


@transaction.atomic
def duplicate_plan(user, plan: Plan) -> Plan:
    """Copy days, focus muscles, and items into a new draft."""
    _ensure_owner(user, plan)
    copy = Plan.objects.create(
        user=user,
        name=_unique_copy_name(user, plan.name),
        split_type=plan.split_type,
        start_date=plan.start_date,
        length_weeks=plan.length_weeks,
    )
    for day in plan.days.prefetch_related("focus_muscles", "items").order_by("weekday"):
        new_day = PlanDay.objects.create(
            plan=copy,
            name=day.name,
            weekday=day.weekday,
            order=day.order,
        )
        new_day.focus_muscles.set(day.focus_muscles.all())
        for item in day.items.all():
            PlanItem.objects.create(
                plan_day=new_day,
                exercise=item.exercise,
                order=item.order,
                superset_group=item.superset_group,
                target_sets=item.target_sets,
                rep_min=item.rep_min,
                rep_max=item.rep_max,
                target_seconds=item.target_seconds,
                target_distance_mi=item.target_distance_mi,
                rest_seconds=item.rest_seconds,
                notes=item.notes,
            )
    return copy


def _unique_copy_name(user, name: str) -> str:
    base = f"{name} (copy)"
    if len(base) > 100:
        base = f"{base[:96]}…)"
    candidate = base
    counter = 2
    while Plan.objects.filter(user=user, name=candidate).exists():
        suffix = f" {counter}"
        candidate = f"{base[: 100 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


# --- Plan days --------------------------------------------------------------


def _resolve_focus_muscles(focus_muscle_ids) -> list[MuscleGroup]:
    ids = [int(value) for value in focus_muscle_ids]
    muscles = list(MuscleGroup.objects.filter(pk__in=ids))
    if len(muscles) != len(set(ids)):
        raise ValidationError({"focus_muscles": "Choose valid muscle groups."})
    return muscles


@transaction.atomic
def add_day(
    user,
    plan: Plan,
    *,
    name: str,
    weekday: int,
    focus_muscle_ids=(),
    today=None,
) -> PlanDay:
    _ensure_owner(user, plan)
    if plan.days.filter(weekday=weekday).exists():
        raise ValidationError({"weekday": "That weekday already has a day in this plan."})
    day = PlanDay(
        plan=plan,
        name=_clean_name(name),
        weekday=int(weekday),
        order=int(weekday),
    )
    day.full_clean()
    day.save()
    day.focus_muscles.set(_resolve_focus_muscles(focus_muscle_ids))
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))
    return day


@transaction.atomic
def update_day(
    user,
    day: PlanDay,
    *,
    name: str,
    weekday: int,
    focus_muscle_ids=(),
    today=None,
) -> PlanDay:
    plan = day.plan
    _ensure_owner(user, plan)
    clash = plan.days.filter(weekday=weekday).exclude(pk=day.pk).exists()
    if clash:
        raise ValidationError({"weekday": "That weekday already has a day in this plan."})
    day.name = _clean_name(name)
    day.weekday = int(weekday)
    day.order = int(weekday)
    day.full_clean()
    day.save()
    day.focus_muscles.set(_resolve_focus_muscles(focus_muscle_ids))
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))
    return day


@transaction.atomic
def delete_day(user, day: PlanDay, *, today=None) -> None:
    """Delete a day unless it has past or completed scheduled workouts."""
    plan = day.plan
    _ensure_owner(user, plan)
    today = _today_or_now(today)
    blocked = day.scheduled_workouts.filter(
        Q(status__in=["COMPLETED", "MADE_UP"]) | Q(scheduled_date__lt=today)
    ).exists()
    if blocked:
        raise ValidationError("This day has past or completed workouts. Archive the plan instead.")
    day.delete()
    if plan.is_active:
        scheduling.regenerate_future(plan, today)


# --- Plan items -------------------------------------------------------------


def clean_item_targets(
    exercise: Exercise,
    *,
    target_sets=3,
    rep_min=None,
    rep_max=None,
    target_seconds=None,
    target_distance_mi=None,
    rest_seconds=90,
) -> dict:
    """Validate targets for the exercise's tracking type and normalize them."""
    errors = {}

    def as_int(value, field, *, minimum=None, maximum=None):
        if value in (None, ""):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            errors[field] = "Enter a whole number."
            return None
        if minimum is not None and number < minimum:
            errors[field] = f"Use {minimum} or more."
        if maximum is not None and number > maximum:
            errors[field] = f"Use {maximum} or less."
        return number

    sets = as_int(target_sets, "target_sets", minimum=1, maximum=99) or 1
    rep_min = as_int(rep_min, "rep_min", minimum=1, maximum=999)
    rep_max = as_int(rep_max, "rep_max", minimum=1, maximum=999)
    seconds = as_int(target_seconds, "target_seconds", minimum=1, maximum=86400)
    rest = as_int(rest_seconds, "rest_seconds", minimum=0, maximum=3600)
    distance = None
    if target_distance_mi not in (None, ""):
        try:
            distance = round(float(target_distance_mi), 2)
        except (TypeError, ValueError):
            errors["target_distance_mi"] = "Enter a distance in miles."
        else:
            if distance < 0:
                errors["target_distance_mi"] = "Distance can't be negative."
            elif distance > 9999:
                errors["target_distance_mi"] = "Keep distance under 10,000 miles."

    tracking = exercise.tracking_type
    if tracking in (Exercise.TrackingType.WEIGHT_REPS, Exercise.TrackingType.BODYWEIGHT):
        if rep_min is None:
            errors["rep_min"] = "Enter the low end of the rep range."
        if rep_max is None:
            errors["rep_max"] = "Enter the high end of the rep range."
        if rep_min is not None and rep_max is not None and rep_min > rep_max:
            errors["rep_max"] = "Max reps must be at least min reps."
        seconds = None
        distance = None
    elif tracking == Exercise.TrackingType.TIMED:
        if seconds is None:
            errors["target_seconds"] = "Enter the target time."
        rep_min = None
        rep_max = None
        distance = None
    elif tracking == Exercise.TrackingType.CARDIO:
        sets = 1
        rep_min = None
        rep_max = None
        if seconds is None and distance is None:
            errors["target_seconds"] = "Add a duration or a distance."
    elif tracking == Exercise.TrackingType.WEIGHT_DISTANCE:
        rep_min = None
        rep_max = None
        seconds = None
    else:
        errors["exercise"] = "That exercise has an unknown tracking type."

    if rest is None:
        rest = 90
    if errors:
        raise ValidationError(errors)
    return {
        "target_sets": sets,
        "rep_min": rep_min,
        "rep_max": rep_max,
        "target_seconds": seconds,
        "target_distance_mi": distance,
        "rest_seconds": rest,
    }


@transaction.atomic
def add_item(user, day: PlanDay, *, exercise: Exercise, today=None, **targets) -> PlanItem:
    plan = day.plan
    _ensure_owner(user, plan)
    if not Exercise.objects.visible_to(user).filter(pk=exercise.pk).exists():
        raise ValidationError({"exercise": "Choose an exercise from your library."})
    notes = (targets.pop("notes", "") or "").strip()
    superset_group = targets.pop("superset_group", "") or ""
    cleaned = clean_item_targets(exercise, **targets)
    max_order = day.items.aggregate(value=Max("order"))["value"]
    next_order = 0 if max_order is None else max_order + 1
    item = PlanItem(
        plan_day=day,
        exercise=exercise,
        order=next_order,
        notes=notes,
        superset_group=superset_group,
        **cleaned,
    )
    item.full_clean()
    item.save()
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))
    return item


@transaction.atomic
def update_item(user, item: PlanItem, *, exercise: Exercise, today=None, **targets) -> PlanItem:
    plan = item.plan_day.plan
    _ensure_owner(user, plan)
    if not Exercise.objects.visible_to(user).filter(pk=exercise.pk).exists():
        raise ValidationError({"exercise": "Choose an exercise from your library."})
    notes = (targets.pop("notes", "") or "").strip()
    targets.pop("superset_group", None)
    cleaned = clean_item_targets(exercise, **targets)
    item.exercise = exercise
    item.notes = notes
    for field, value in cleaned.items():
        setattr(item, field, value)
    item.full_clean()
    item.save()
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))
    return item


@transaction.atomic
def delete_item(user, item: PlanItem, *, today=None) -> None:
    day = item.plan_day
    plan = day.plan
    _ensure_owner(user, plan)
    item.delete()
    _renumber(day)
    _normalize_superset_groups(day)
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))


def _renumber(day: PlanDay) -> None:
    items = list(day.items.order_by("order", "pk"))
    now = timezone.now()
    changed = []
    for index, item in enumerate(items):
        if item.order != index:
            item.order = index
            item.updated_at = now
            changed.append(item)
    if changed:
        PlanItem.objects.bulk_update(changed, ["order", "updated_at"])


def _save_order(ordered: list[PlanItem]) -> None:
    now = timezone.now()
    for index, item in enumerate(ordered):
        item.order = index
        item.updated_at = now
    PlanItem.objects.bulk_update(ordered, ["order", "updated_at"])


def _sequence_is_contiguous(ordered: list[PlanItem]) -> bool:
    seen = set()
    previous = None
    for item in ordered:
        group = item.superset_group
        if not group:
            previous = None
            continue
        if group == previous:
            continue
        if group in seen:
            return False
        seen.add(group)
        previous = group
    return True


def _assert_contiguous(day: PlanDay) -> None:
    if not _sequence_is_contiguous(list(day.items.order_by("order", "pk"))):
        raise ValidationError("Superset exercises must stay together.")


def _normalize_superset_groups(day: PlanDay) -> None:
    items = list(day.items.order_by("order", "pk"))
    counts = Counter(item.superset_group for item in items if item.superset_group)
    now = timezone.now()
    changed = []
    for item in items:
        if item.superset_group and counts[item.superset_group] < 2:
            item.superset_group = ""
            item.updated_at = now
            changed.append(item)
    if changed:
        PlanItem.objects.bulk_update(changed, ["superset_group", "updated_at"])


def _block_bounds(items, index):
    group = items[index].superset_group
    if not group:
        return index, index
    start = index
    while start > 0 and items[start - 1].superset_group == group:
        start -= 1
    end = index
    while end + 1 < len(items) and items[end + 1].superset_group == group:
        end += 1
    return start, end


@transaction.atomic
def move_item(user, item: PlanItem, direction: str, *, today=None) -> None:
    """Move an item (or its whole superset block) one block up or down."""
    day = item.plan_day
    plan = day.plan
    _ensure_owner(user, plan)
    if direction not in {"up", "down"}:
        raise ValidationError("Choose up or down.")
    items = list(day.items.order_by("order", "pk"))
    index = next(position for position, row in enumerate(items) if row.pk == item.pk)
    block_start, block_end = _block_bounds(items, index)

    if direction == "up":
        if block_start == 0:
            return
        neighbour_start, _ = _block_bounds(items, block_start - 1)
        ordered = (
            items[:neighbour_start]
            + items[block_start : block_end + 1]
            + items[neighbour_start:block_start]
            + items[block_end + 1 :]
        )
    else:
        if block_end == len(items) - 1:
            return
        _, neighbour_end = _block_bounds(items, block_end + 1)
        ordered = (
            items[:block_start]
            + items[block_end + 1 : neighbour_end + 1]
            + items[block_start : block_end + 1]
            + items[neighbour_end + 1 :]
        )

    if not _sequence_is_contiguous(ordered):
        raise ValidationError("Superset exercises must stay together.")
    _save_order(ordered)
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))


@transaction.atomic
def reorder_items(user, day: PlanDay, ordered_ids, *, today=None) -> None:
    """Persist a drag-and-drop order after validating the submitted id list."""
    plan = day.plan
    _ensure_owner(user, plan)
    items = list(day.items.order_by("order", "pk"))
    try:
        ids = [int(value) for value in ordered_ids]
    except (TypeError, ValueError) as error:
        raise ValidationError("The exercise order was invalid. Refresh and try again.") from error
    if len(ids) != len(items) or set(ids) != {item.pk for item in items}:
        raise ValidationError("The exercise list changed. Refresh and try again.")
    by_id = {item.pk: item for item in items}
    ordered = [by_id[pk] for pk in ids]
    if not _sequence_is_contiguous(ordered):
        raise ValidationError("That order would split a superset. Keep its exercises together.")
    _save_order(ordered)
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))


@transaction.atomic
def create_superset(user, day: PlanDay, item_ids, *, today=None) -> str:
    """Group two or more consecutive items into the next free superset label."""
    plan = day.plan
    _ensure_owner(user, plan)
    try:
        ids = [int(value) for value in item_ids]
    except (TypeError, ValueError) as error:
        raise ValidationError("Choose exercises to group.") from error
    if len(set(ids)) < 2:
        raise ValidationError("Select at least two exercises for a superset.")

    items = list(day.items.order_by("order", "pk"))
    positions = {item.pk: index for index, item in enumerate(items)}
    if any(pk not in positions for pk in ids):
        raise ValidationError("Choose exercises from this day.")
    indices = sorted(positions[pk] for pk in set(ids))
    if indices != list(range(indices[0], indices[-1] + 1)):
        raise ValidationError("Select consecutive exercises to make a superset.")

    selected = [items[index] for index in indices]
    used = {item.superset_group for item in items if item.superset_group and item not in selected}
    label = next((candidate for candidate in SUPERSET_LABELS if candidate not in used), None)
    if label is None:
        raise ValidationError("This day already has the maximum number of supersets.")

    for item in selected:
        item.superset_group = label
        item.updated_at = timezone.now()
    PlanItem.objects.bulk_update(selected, ["superset_group", "updated_at"])
    _normalize_superset_groups(day)
    _assert_contiguous(day)
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))
    return label


@transaction.atomic
def clear_superset(user, day: PlanDay, group: str, *, today=None) -> None:
    plan = day.plan
    _ensure_owner(user, plan)
    if group not in SUPERSET_LABELS:
        raise ValidationError("That superset no longer exists.")
    day.items.filter(superset_group=group).update(superset_group="", updated_at=timezone.now())
    if plan.is_active:
        scheduling.regenerate_future(plan, _today_or_now(today))


# --- Display helpers --------------------------------------------------------


def weekday_labels(plan: Plan) -> str:
    """Short weekday labels for a plan, e.g. ``M T Th F``."""
    letters = {0: "M", 1: "T", 2: "W", 3: "Th", 4: "F", 5: "S", 6: "Su"}
    return " ".join(letters[day.weekday] for day in plan.days.all())
