"""Plan builder and scheduling views (F-03, F-04)."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.exercises.forms import ExerciseForm
from apps.exercises.models import Exercise
from apps.exercises.services.library import create_exercise

from .forms import PlanDayForm, PlanForm, PlanItemForm
from .models import Plan, ScheduledWorkout, Weekday
from .services import scheduling
from .services.plans import (
    add_day,
    add_item,
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
from .services.today import build_today


def plans(request):
    """Plan list grouped by active, drafts, and archived."""
    groups = list_plans(request.user)
    for group in groups.values():
        for plan in group:
            plan.weekday_labels = weekday_labels(plan)
    return render(
        request,
        "plans/list.html",
        {
            "page_title": "Plan",
            "groups": groups,
            "has_plans": any(groups.values()),
        },
    )


def plan_new(request):
    """Create a draft plan."""
    if request.method == "POST":
        form = PlanForm(request.POST)
        if form.is_valid():
            plan = create_plan(
                request.user,
                name=form.cleaned_data["name"],
                split_type=form.cleaned_data["split_type"],
                start_date=form.cleaned_data["start_date"],
                length_weeks=form.cleaned_data["length_weeks"],
            )
            messages.success(request, f"Created {plan.name}.")
            return redirect("plan_detail", pk=plan.pk)
    else:
        form = PlanForm(initial={"start_date": timezone.localdate()})

    return render(
        request,
        "plans/form.html",
        {
            "page_title": "New plan",
            "form": form,
        },
    )


def _decorate_day(day, *, items=None):
    """Attach the display data shared by the day card and its items partial."""
    day.items_list = (
        list(items)
        if items is not None
        else list(day.items.select_related("exercise").order_by("order"))
    )
    day.focus_list = list(day.focus_muscles.all())
    day.superset_groups = sorted(
        {item.superset_group for item in day.items_list if item.superset_group}
    )
    return day


def _day_items_response(request, plan, day):
    """Render the in-place items region, plus out-of-band messages."""
    _decorate_day(day)
    return render(
        request,
        "plans/_day_items_swap.html",
        {
            "plan": plan,
            "day": day,
        },
    )


def _detail_context(
    request,
    plan,
    *,
    plan_form=None,
    add_day_form=None,
    day_form=None,
    edit_day_id=None,
):
    today = timezone.localdate()
    days = list(plan.days.prefetch_related("focus_muscles", "items__exercise").order_by("weekday"))
    for day in days:
        _decorate_day(day, items=day.items.all())
        if edit_day_id == day.pk and day_form is not None:
            day.edit_form = day_form
        else:
            day.edit_form = PlanDayForm(instance=day, plan=plan)

    used_weekdays = {day.weekday for day in days}
    free_weekdays = [value for value, _label in Weekday.choices if value not in used_weekdays]
    if add_day_form is None and free_weekdays:
        add_day_form = PlanDayForm(plan=plan, initial={"weekday": free_weekdays[0]})

    other_active = Plan.objects.active_for(request.user).exclude(pk=plan.pk).first()
    return {
        "page_title": plan.name,
        "plan": plan,
        "days": days,
        "plan_form": plan_form or PlanForm(instance=plan),
        "add_day_form": add_day_form,
        "free_weekdays": free_weekdays,
        "other_active_plan": other_active,
        "week_number": scheduling.week_number(plan, today) if plan.is_active else None,
        "weekday_labels": weekday_labels(plan),
        "today": today,
    }


def plan_detail(request, pk):
    """Plan settings and the phone-first list builder."""
    plan = get_plan(request.user, pk)
    if request.method == "POST":
        form = PlanForm(request.POST, instance=plan)
        if form.is_valid():
            try:
                update_plan(
                    request.user,
                    plan,
                    name=form.cleaned_data["name"],
                    split_type=form.cleaned_data["split_type"],
                    start_date=form.cleaned_data["start_date"],
                    length_weeks=form.cleaned_data["length_weeks"],
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Plan saved.")
                return redirect("plan_detail", pk=plan.pk)
        return render(
            request,
            "plans/detail.html",
            _detail_context(request, plan, plan_form=form),
        )

    return render(request, "plans/detail.html", _detail_context(request, plan))


@require_POST
def plan_day_add(request, pk):
    plan = get_plan(request.user, pk)
    form = PlanDayForm(request.POST, plan=plan)
    if form.is_valid():
        try:
            day = add_day(
                request.user,
                plan,
                name=form.cleaned_data["name"],
                weekday=form.cleaned_data["weekday"],
                focus_muscle_ids=[muscle.pk for muscle in form.cleaned_data["focus_muscles"]],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Day added.")
            return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-{day.pk}")
    return render(
        request,
        "plans/detail.html",
        _detail_context(request, plan, add_day_form=form),
    )


@require_POST
def plan_day_edit(request, pk, day_id):
    plan = get_plan(request.user, pk)
    day = get_plan_day(request.user, pk, day_id)
    form = PlanDayForm(request.POST, instance=day, plan=plan)
    if form.is_valid():
        try:
            update_day(
                request.user,
                day,
                name=form.cleaned_data["name"],
                weekday=form.cleaned_data["weekday"],
                focus_muscle_ids=[muscle.pk for muscle in form.cleaned_data["focus_muscles"]],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Day updated.")
            return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-{day.pk}")
    return render(
        request,
        "plans/detail.html",
        _detail_context(
            request,
            plan,
            day_form=form,
            edit_day_id=day.pk,
        ),
    )


@require_POST
def plan_day_delete(request, pk, day_id):
    plan = get_plan(request.user, pk)
    day = get_plan_day(request.user, pk, day_id)
    if request.POST.get("confirm") != "1":
        return _render_confirm(
            request,
            title="Delete day?",
            message=f"Delete {day.name} and its exercises? Scheduled workouts from today on will be removed.",
            confirm_label="Delete day",
            cancel_href=reverse("plan_detail", args=[plan.pk]),
        )
    try:
        delete_day(request.user, day)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Day deleted.")
    return redirect("plan_detail", pk=plan.pk)


def plan_item_new(request, pk, day_id):
    """Add an exercise to a day. Supports inline exercise creation."""
    plan = get_plan(request.user, pk)
    day = get_plan_day(request.user, pk, day_id)
    inline_form = ExerciseForm(
        user=request.user,
        initial={"tracking_type": Exercise.TrackingType.WEIGHT_REPS},
    )

    if request.method == "POST" and request.POST.get("form_name") == "exercise":
        inline_form = ExerciseForm(request.POST, user=request.user)
        if inline_form.is_valid():
            exercise = create_exercise(user=request.user, **inline_form.cleaned_data)
            messages.success(request, f"Added {exercise.name}.")
            url = reverse("plan_item_new", args=[plan.pk, day.pk])
            return redirect(f"{url}?exercise={exercise.pk}")
        item_form = PlanItemForm(user=request.user, day=day)
    elif request.method == "POST":
        item_form = PlanItemForm(request.POST, user=request.user, day=day)
        if item_form.is_valid():
            data = item_form.cleaned_data.copy()
            exercise = data.pop("exercise")
            try:
                add_item(request.user, day, exercise=exercise, **data)
            except ValidationError as error:
                item_form.add_error(None, error)
            else:
                messages.success(request, "Exercise added.")
                return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-items-{day.pk}")
    else:
        initial = {}
        exercise_id = request.GET.get("exercise")
        if exercise_id:
            initial["exercise"] = exercise_id
        item_form = PlanItemForm(initial=initial, user=request.user, day=day)

    query = request.GET.get("q", "").strip()
    return render(
        request,
        "plans/item_form.html",
        {
            "page_title": "Add exercise",
            "plan": plan,
            "day": day,
            "form": item_form,
            "inline_form": inline_form,
            "picker_groups": picker_exercises(request.user, day, query=query),
            "query": query,
            "is_edit": False,
            "selected_tracking": item_form.selected_tracking,
            "focus_muscles": list(day.focus_muscles.all()),
        },
    )


def plan_item_edit(request, pk, item_id):
    plan = get_plan(request.user, pk)
    item = get_plan_item(request.user, pk, item_id)
    day = item.plan_day
    if request.method == "POST":
        form = PlanItemForm(request.POST, instance=item, user=request.user, day=day)
        if form.is_valid():
            data = form.cleaned_data.copy()
            exercise = data.pop("exercise")
            try:
                update_item(request.user, item, exercise=exercise, **data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Exercise updated.")
                return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-items-{day.pk}")
    else:
        form = PlanItemForm(instance=item, user=request.user, day=day)

    return render(
        request,
        "plans/item_form.html",
        {
            "page_title": "Edit exercise",
            "plan": plan,
            "day": day,
            "item": item,
            "form": form,
            "inline_form": None,
            "picker_groups": [],
            "query": "",
            "is_edit": True,
            "selected_tracking": form.selected_tracking,
            "focus_muscles": list(day.focus_muscles.all()),
        },
    )


@require_POST
def plan_item_delete(request, pk, item_id):
    plan = get_plan(request.user, pk)
    item = get_plan_item(request.user, pk, item_id)
    if request.POST.get("confirm") != "1":
        return _render_confirm(
            request,
            title="Delete exercise?",
            message=f"Remove {item.exercise.name} from {item.plan_day.name}?",
            confirm_label="Delete exercise",
            cancel_href=reverse("plan_detail", args=[plan.pk]),
        )
    delete_item(request.user, item)
    messages.success(request, "Exercise removed.")
    return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-items-{item.plan_day_id}")


@require_POST
def plan_item_move(request, pk, item_id):
    plan = get_plan(request.user, pk)
    item = get_plan_item(request.user, pk, item_id)
    try:
        move_item(request.user, item, request.POST.get("direction", ""))
    except ValidationError as error:
        messages.error(request, error.messages[0])
    if request.htmx:
        return _day_items_response(request, plan, item.plan_day)
    return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-items-{item.plan_day_id}")


@require_POST
def plan_day_reorder(request, pk, day_id):
    plan = get_plan(request.user, pk)
    day = get_plan_day(request.user, pk, day_id)
    ordered_ids = request.POST.get("ordered_ids", "").split(",")
    try:
        reorder_items(request.user, day, ordered_ids)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Order saved.")
    if request.htmx:
        return _day_items_response(request, plan, day)
    return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-items-{day.pk}")


@require_POST
def plan_day_superset(request, pk, day_id):
    plan = get_plan(request.user, pk)
    day = get_plan_day(request.user, pk, day_id)
    try:
        label = create_superset(request.user, day, request.POST.getlist("item_ids"))
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"Superset {label} created.")
    if request.htmx:
        return _day_items_response(request, plan, day)
    return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-items-{day.pk}")


@require_POST
def plan_day_superset_clear(request, pk, day_id):
    plan = get_plan(request.user, pk)
    day = get_plan_day(request.user, pk, day_id)
    try:
        clear_superset(request.user, day, request.POST.get("group", ""))
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Superset removed.")
    if request.htmx:
        return _day_items_response(request, plan, day)
    return redirect(f"{reverse('plan_detail', args=[plan.pk])}#day-items-{day.pk}")


@require_POST
def plan_activate(request, pk):
    plan = get_plan(request.user, pk)
    if plan.is_active:
        messages.info(request, f"{plan.name} is already active.")
        return redirect("plan_detail", pk=plan.pk)
    other = Plan.objects.active_for(request.user).exclude(pk=plan.pk).first()
    if other is not None and request.POST.get("confirm") != "1":
        return _render_confirm(
            request,
            title="Activate plan?",
            message=(
                f"This archives {other.name} and removes its future pending workouts. "
                f"{plan.name} becomes your active plan."
            ),
            confirm_label="Activate plan",
            cancel_href=reverse("plan_detail", args=[plan.pk]),
        )
    scheduling.activate_plan(plan, timezone.localdate())
    messages.success(request, f"{plan.name} is now active.")
    return redirect("plan_detail", pk=plan.pk)


@require_POST
def plan_archive(request, pk):
    plan = get_plan(request.user, pk)
    if plan.is_archived:
        messages.info(request, f"{plan.name} is already archived.")
        return redirect("plan_detail", pk=plan.pk)
    if request.POST.get("confirm") != "1":
        return _render_confirm(
            request,
            title="Archive plan?",
            message=(
                f"Archive {plan.name}? Future pending workouts are removed. "
                "Completed history is kept."
            ),
            confirm_label="Archive plan",
            cancel_href=reverse("plan_detail", args=[plan.pk]),
        )
    scheduling.archive_plan(plan, timezone.localdate())
    messages.success(request, f"Archived {plan.name}.")
    return redirect("plans")


@require_POST
def plan_duplicate(request, pk):
    plan = get_plan(request.user, pk)
    copy = duplicate_plan(request.user, plan)
    messages.success(request, f"Created {copy.name}.")
    return redirect("plan_detail", pk=copy.pk)


def plan_picker(request, pk):
    """HTMX exercise picker partial, focus groups first."""
    plan = get_plan(request.user, pk)
    day_id = request.GET.get("day")
    day = get_plan_day(request.user, pk, day_id)
    query = request.GET.get("q", "").strip()
    return render(
        request,
        "plans/_picker.html",
        {
            "plan": plan,
            "day": day,
            "query": query,
            "picker_groups": picker_exercises(request.user, day, query=query),
            "focus_muscles": list(day.focus_muscles.all()),
        },
    )


@require_POST
def scheduled_mark_missed(request, pk):
    workout = get_object_or_404(ScheduledWorkout.objects.for_user(request.user), pk=pk)
    try:
        scheduling.mark_missed(workout, timezone.localdate())
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Marked as missed.")
    if request.htmx:
        today_date = timezone.localdate()
        context = build_today(request.user, today_date)
        context.update({"page_title": "Today", "today": today_date})
        return render(request, "core/_today_swap.html", context)
    return redirect("today")


def _render_confirm(request, *, title, message, confirm_label, cancel_href):
    return render(
        request,
        "plans/confirm.html",
        {
            "page_title": title,
            "confirm_title": title,
            "confirm_message": message,
            "confirm_label": confirm_label,
            "cancel_href": cancel_href,
        },
    )
