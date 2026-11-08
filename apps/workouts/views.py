"""Workout runner, unscheduled sessions, tags, and history views (F-05, F-06, F-09)."""

import uuid
from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.services.settings import get_settings
from apps.exercises.models import Exercise
from apps.exercises.services.library import grouped_by_muscle, list_exercises
from apps.plans.models import Plan, ScheduledWorkout

from .forms import (
    RetroSessionForm,
    SessionEditForm,
    SessionItemFormSet,
    SetLogForm,
    TagForm,
    UnscheduledSessionForm,
)
from .models import Session, SessionExercise, SetLog, Tag
from .services import history, progression, runner
from .services import sessions as session_services
from .services import summary as summary_services
from .services import tags as tag_services


def _get_session(user, pk) -> Session:
    return get_object_or_404(
        Session.objects.filter(user=user)
        .select_related(
            "plan_day",
            "scheduled_workout",
            "scheduled_workout__plan",
            "scheduled_workout__plan_day",
        )
        .prefetch_related("tags"),
        pk=pk,
    )


def _get_set_log(user, pk) -> SetLog:
    return get_object_or_404(
        SetLog.objects.filter(session_exercise__session__user=user).select_related(
            "session_exercise",
            "session_exercise__exercise",
            "session_exercise__session",
        ),
        pk=pk,
    )


def _get_session_exercise(session: Session, raw_id) -> SessionExercise:
    try:
        pk = int(raw_id)
    except (TypeError, ValueError):
        pk = None
    return get_object_or_404(
        SessionExercise.objects.filter(session=session).select_related("exercise"),
        pk=pk,
    )


def _decimal_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"


def _duration_text(seconds) -> str:
    if seconds in (None, ""):
        return ""
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return str(seconds)
    minutes, remainder = divmod(total, 60)
    return f"{minutes}:{remainder:02d}"


def _prefill_values(user, session_exercise: SessionExercise, set_number: int) -> dict:
    data = progression.prefill(user, session_exercise, set_number)
    return {
        "weight_lb": _decimal_text(data["weight_lb"]),
        "reps": "" if data["reps"] is None else data["reps"],
        "duration_seconds": "" if data["duration_seconds"] is None else data["duration_seconds"],
        "duration": _duration_text(data["duration_seconds"]),
        "distance_mi": _decimal_text(data["distance_mi"]),
        "difficulty": "",
    }


def _ordered_exercises(session: Session) -> list[SessionExercise]:
    return list(
        session.session_exercises.select_related("exercise")
        .prefetch_related("sets")
        .order_by("order", "pk")
    )


def _reorder_blocks(session: Session) -> tuple[list[dict], list[dict]]:
    """Group exercises for the reorder sheet, with edge flags per block."""
    locked: list[dict] = []
    movable: list[dict] = []
    for block in runner.exercise_blocks(session):
        entry = {
            "exercises": block,
            "locked": runner.block_is_locked(block),
        }
        (locked if entry["locked"] else movable).append(entry)
    for index, entry in enumerate(movable):
        entry["is_first"] = index == 0
        entry["is_last"] = index == len(movable) - 1
    return locked, movable


def _runner_context(
    request,
    session: Session,
    *,
    rest_seconds: int = 0,
    panel: str | None = None,
    values=None,
    save_failed: bool = False,
) -> dict:
    exercises = _ordered_exercises(session)
    step = runner.next_step(session)
    context = {
        "page_title": session.title,
        "session": session,
        "completed": session.is_completed,
        "panel": panel,
        "exercises": exercises,
        "has_exercises": bool(exercises),
        "locked_exercises": [],
        "movable_exercises": [],
        "locked_blocks": [],
        "movable_blocks": [],
        "jump_exercises": [],
        "increase_exercises": [],
        "picker_groups": [],
        "query": "",
        "step": step,
        "session_exercise": None,
        "tracking_type": "",
        "values": values or {},
        "last_time": "",
        "increase": False,
        "done_sets": [],
        "exercise_position": 0,
        "exercise_total": len(exercises),
        "rest_seconds": 0,
        "timer_sound": get_settings(request.user).timer_sound,
        "client_id": uuid.uuid4(),
        "difficulty_range": range(1, 11),
        "save_failed": save_failed,
    }

    if step is not None:
        session_exercise = step.session_exercise
        context.update(
            {
                "session_exercise": session_exercise,
                "tracking_type": session_exercise.exercise.tracking_type,
                "values": values
                if values is not None
                else _prefill_values(request.user, session_exercise, step.set_number),
                "last_time": progression.last_time_display(request.user, session_exercise),
                "increase": progression.flag_for_upcoming(
                    request.user,
                    session_exercise.exercise,
                    session.plan_day,
                ),
                "done_sets": session_exercise.done_sets,
                "exercise_position": runner.step_context(session, step)["exercise_position"],
                "rest_seconds": rest_seconds if rest_seconds > 0 else 0,
            }
        )

    if panel == "reorder":
        locked_blocks, movable_blocks = _reorder_blocks(session)
        context["locked_blocks"] = locked_blocks
        context["movable_blocks"] = movable_blocks
        context["locked_exercises"] = [
            exercise for entry in locked_blocks for exercise in entry["exercises"]
        ]
        context["movable_exercises"] = [
            exercise for entry in movable_blocks for exercise in entry["exercises"]
        ]
    elif panel == "jump":
        context["jump_exercises"] = [exercise for exercise in exercises if not exercise.is_complete]
    elif panel == "add":
        query = request.GET.get("q", "").strip()
        context["query"] = query
        context["picker_groups"] = grouped_by_muscle(list_exercises(user=request.user, query=query))
    elif panel == "menu":
        context["increase_exercises"] = [
            exercise
            for exercise in exercises
            if exercise.status in (SessionExercise.Status.DONE, SessionExercise.Status.IN_PROGRESS)
        ]

    if session.is_completed or step is None:
        context["increase_exercises"] = [
            exercise for exercise in exercises if progression.increase_flag(exercise)
        ]
    context["summary"] = summary_services.build_summary(session) if session.is_completed else None
    return context


def _runner_response(request, session: Session, **kwargs):
    return render(
        request,
        "workouts/_runner_swap.html",
        _runner_context(request, session, **kwargs),
    )


def _finish_or_redirect(request, session: Session, **kwargs):
    panel = request.POST.get("panel")
    if panel in ("menu", "reorder", "jump", "add") and "panel" not in kwargs:
        kwargs["panel"] = panel
    if request.htmx:
        return _runner_response(request, session, **kwargs)
    return redirect("session_run", pk=session.pk)


@require_POST
def scheduled_start(request, pk):
    """Start (or resume) a Scheduled Workout from Today."""
    workout = get_object_or_404(ScheduledWorkout.objects.for_user(request.user), pk=pk)
    existing = Session.objects.filter(
        user=request.user,
        status=Session.Status.IN_PROGRESS,
    ).first()
    if existing is not None:
        messages.info(request, "Finish or discard your current workout first.")
        return redirect("session_run", pk=existing.pk)
    try:
        session = runner.start_scheduled_session(request.user, workout)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("today")
    messages.success(request, f"Started {session.title}.")
    return redirect("session_run", pk=session.pk)


def session_run(request, pk):
    """Runner page: the current step, or the completion card."""
    session = _get_session(request.user, pk)
    panel = request.GET.get("panel")
    if panel not in ("menu", "reorder", "jump", "add"):
        panel = None
    if request.htmx and request.headers.get("HX-Target") == "runner":
        return _runner_response(request, session, panel=panel)
    return render(
        request,
        "workouts/run.html",
        _runner_context(request, session, panel=panel),
    )


@require_POST
def session_log_set(request, pk):
    session = _get_session(request.user, pk)
    session_exercise = _get_session_exercise(session, request.POST.get("exercise"))
    step = runner.next_step(session)
    rest = 0
    if step is not None and step.session_exercise.pk == session_exercise.pk:
        rest = step.rest_after_seconds
    try:
        runner.log_set(
            session,
            session_exercise,
            request.POST,
            client_id=request.POST.get("client_id") or None,
        )
    except ValidationError as error:
        messages.error(request, f"Couldn't save — {error.messages[0]}")
        return _finish_or_redirect(
            request,
            session,
            values=request.POST,
            save_failed=True,
        )
    return _finish_or_redirect(request, session, rest_seconds=rest)


@require_POST
def session_skip_set(request, pk):
    session = _get_session(request.user, pk)
    session_exercise = _get_session_exercise(session, request.POST.get("exercise"))
    try:
        runner.skip_set(
            session,
            session_exercise,
            client_id=request.POST.get("client_id") or None,
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return _finish_or_redirect(request, session)


@require_POST
def session_add_set(request, pk):
    session = _get_session(request.user, pk)
    session_exercise = _get_session_exercise(session, request.POST.get("exercise"))
    try:
        runner.add_set(session, session_exercise)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return _finish_or_redirect(request, session)


@require_POST
def session_skip_exercise(request, pk):
    session = _get_session(request.user, pk)
    session_exercise = _get_session_exercise(session, request.POST.get("exercise"))
    try:
        runner.skip_exercise(session, session_exercise)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return _finish_or_redirect(request, session)


@require_POST
def session_add_exercise(request, pk):
    session = _get_session(request.user, pk)
    try:
        exercise = get_object_or_404(
            Exercise.objects.visible_to(request.user),
            pk=request.POST.get("exercise"),
        )
        runner.add_exercise(session, exercise)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, f"Added {exercise.name}.")
    return _finish_or_redirect(request, session)


@require_POST
def session_reorder(request, pk):
    session = _get_session(request.user, pk)
    ordered_ids = [
        value for value in request.POST.get("ordered_ids", "").split(",") if value.strip()
    ]
    try:
        runner.reorder(session, ordered_ids)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Order saved.")
    return _finish_or_redirect(request, session)


@require_POST
def session_move_exercise(request, pk):
    session = _get_session(request.user, pk)
    session_exercise = _get_session_exercise(session, request.POST.get("exercise"))
    try:
        runner.move_exercise(session, session_exercise, request.POST.get("direction", ""))
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return _finish_or_redirect(request, session)


@require_POST
def session_jump(request, pk, exercise_id):
    session = _get_session(request.user, pk)
    session_exercise = _get_session_exercise(session, exercise_id)
    try:
        runner.jump_to(session, session_exercise)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return _finish_or_redirect(request, session)


def session_picker(request, pk):
    """HTMX exercise picker for the add-exercise sheet."""
    session = _get_session(request.user, pk)
    query = request.GET.get("q", "").strip()
    return render(
        request,
        "workouts/_picker.html",
        {
            "session": session,
            "query": query,
            "picker_groups": grouped_by_muscle(list_exercises(user=request.user, query=query)),
        },
    )


@require_POST
def session_finish(request, pk):
    session = _get_session(request.user, pk)
    if session.is_in_progress:
        runner.finish_session(session)
        messages.success(request, "Workout complete.")
    destination = request.POST.get("next")
    if request.htmx:
        return _runner_response(request, session)
    if destination == "today":
        return redirect("today")
    return redirect("session_run", pk=session.pk)


@require_POST
def session_discard(request, pk):
    session = _get_session(request.user, pk)
    destination = request.POST.get("next")
    cancel_href = (
        reverse("today") if destination == "today" else reverse("session_run", args=[session.pk])
    )
    if request.POST.get("confirm") != "1":
        return render(
            request,
            "plans/confirm.html",
            {
                "page_title": "Discard workout?",
                "confirm_title": "Discard workout?",
                "confirm_message": (
                    f"Discard {session.title}? Every set logged in this workout is deleted."
                ),
                "confirm_label": "Discard workout",
                "cancel_href": cancel_href,
            },
        )
    if not session.is_in_progress:
        messages.error(request, "That workout is already finished.")
        return redirect("today")
    runner.discard_session(session, timezone.localdate())
    messages.success(request, "Workout discarded.")
    return redirect("today")


# --- Unscheduled sessions ---------------------------------------------------


def _first_form_error(form) -> str:
    for error in form.non_field_errors():
        return str(error)
    for errors in form.errors.values():
        for error in errors:
            return str(error)
    return "Couldn't save that set."


def _items_from_formset(formset):
    return [
        form.cleaned_data
        for form in formset.forms
        if getattr(form, "cleaned_data", None) and form.cleaned_data.get("exercise")
    ]


def _build_item_formset(request):
    """Return the exercise formset, adding a row when ``add_row`` was pressed."""
    data = request.POST.copy()
    adding_row = "add_row" in request.POST
    if adding_row:
        try:
            total = int(data.get("items-TOTAL_FORMS", "0"))
        except (TypeError, ValueError):
            total = 0
        data["items-TOTAL_FORMS"] = str(total + 1)
    formset = SessionItemFormSet(
        data,
        prefix="items",
        form_kwargs={"user": request.user},
    )
    return formset, adding_row


def session_new(request):
    """Plan and start an unscheduled session (F-06)."""
    if request.method == "POST":
        form = UnscheduledSessionForm(request.POST, user=request.user)
        formset, adding_row = _build_item_formset(request)
        if not adding_row and form.is_valid() and formset.is_valid():
            try:
                session = session_services.start_unscheduled_session(
                    request.user,
                    title=form.cleaned_data["title"],
                    tag_ids=[tag.pk for tag in form.cleaned_data["tags"]],
                    items=_items_from_formset(formset),
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f"Started {session.title}.")
                return redirect("session_run", pk=session.pk)
    else:
        form = UnscheduledSessionForm(user=request.user)
        formset = SessionItemFormSet(prefix="items", form_kwargs={"user": request.user})
        adding_row = False

    return render(
        request,
        "workouts/session_new.html",
        {
            "page_title": "Unscheduled session",
            "form": form,
            "formset": formset,
            "adding_row": adding_row,
            "available_tags": tag_services.list_tags(request.user),
        },
    )


def session_log(request):
    """Log a workout that already happened (F-06)."""
    if request.method == "POST":
        form = RetroSessionForm(request.POST, user=request.user)
        formset, adding_row = _build_item_formset(request)
        if not adding_row and form.is_valid() and formset.is_valid():
            try:
                session = session_services.create_retro_session(
                    request.user,
                    title=form.cleaned_data["title"],
                    performed_date=form.cleaned_data["performed_date"],
                    start_time=form.cleaned_data["start_time"],
                    duration_seconds=form.duration_seconds,
                    tag_ids=[tag.pk for tag in form.cleaned_data["tags"]],
                    items=_items_from_formset(formset),
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(
                    request,
                    "Workout logged. Add sets below or edit the workout details.",
                )
                return redirect("session_detail", pk=session.pk)
    else:
        form = RetroSessionForm(
            user=request.user,
            initial={"performed_date": timezone.localdate()},
        )
        formset = SessionItemFormSet(prefix="items", form_kwargs={"user": request.user})
        adding_row = False

    return render(
        request,
        "workouts/session_log.html",
        {
            "page_title": "Log past workout",
            "form": form,
            "formset": formset,
            "adding_row": adding_row,
            "available_tags": tag_services.list_tags(request.user),
        },
    )


# --- Session detail and editing --------------------------------------------


def session_detail(request, pk):
    """Summary-style detail with editable sets (F-09)."""
    session = _get_session(request.user, pk)
    exercises = list(
        session.session_exercises.select_related("exercise")
        .prefetch_related("sets")
        .order_by("order", "pk")
    )
    for exercise in exercises:
        exercise.add_form = SetLogForm(
            tracking_type=exercise.exercise.tracking_type,
            auto_id=f"add-{exercise.pk}-%s",
        )
    return render(
        request,
        "workouts/session_detail.html",
        {
            "page_title": session.title,
            "session": session,
            "exercises": exercises,
            "is_editable": session.is_completed,
            "summary": (summary_services.build_summary(session) if session.is_completed else None),
        },
    )


def session_edit(request, pk):
    """Change a session's title, performed date, and tags."""
    session = _get_session(request.user, pk)
    if request.method == "POST":
        form = SessionEditForm(request.POST, user=request.user, session=session)
        if form.is_valid():
            try:
                session_services.update_session_metadata(
                    request.user,
                    session,
                    title=form.cleaned_data["title"],
                    performed_date=form.cleaned_data["performed_date"],
                    tag_ids=[tag.pk for tag in form.cleaned_data["tags"]],
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Workout updated.")
                return redirect("session_detail", pk=session.pk)
    else:
        form = SessionEditForm(user=request.user, session=session)

    return render(
        request,
        "workouts/session_edit.html",
        {
            "page_title": "Edit workout",
            "session": session,
            "form": form,
            "available_tags": tag_services.list_tags(request.user),
        },
    )


def session_delete(request, pk):
    """Delete a completed session after a confirmation page."""
    session = _get_session(request.user, pk)
    if session.is_in_progress:
        messages.error(request, "Discard an in-progress workout from the runner instead.")
        return redirect("session_run", pk=session.pk)
    if request.method == "POST" and request.POST.get("confirm") == "1":
        try:
            session_services.delete_session(request.user, session)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Workout deleted.")
        return redirect("history")
    return render(
        request,
        "plans/confirm.html",
        {
            "page_title": "Delete workout?",
            "confirm_title": "Delete workout?",
            "confirm_message": (
                f"Delete {session.title} on {session.performed_date:%b} "
                f"{session.performed_date.day}, {session.performed_date.year}? "
                "Every set is deleted too."
            ),
            "confirm_label": "Delete workout",
            "cancel_href": reverse("session_detail", args=[session.pk]),
        },
    )


# --- Set editing ------------------------------------------------------------


def _is_row_request(request, set_log: SetLog) -> bool:
    return request.htmx and request.headers.get("HX-Target") == f"set-{set_log.pk}"


def _set_initial(set_log: SetLog) -> dict:
    return {
        "weight_lb": _decimal_text(set_log.weight_lb),
        "reps": set_log.reps,
        "duration": _duration_text(set_log.duration_seconds),
        "distance_mi": _decimal_text(set_log.distance_mi),
        "difficulty": set_log.difficulty,
    }


@require_POST
def set_add(request, pk):
    session = _get_session(request.user, pk)
    session_exercise = _get_session_exercise(session, request.POST.get("exercise"))
    form = SetLogForm(
        request.POST,
        tracking_type=session_exercise.exercise.tracking_type,
    )
    if form.is_valid():
        try:
            session_services.add_manual_set(
                request.user,
                session,
                session_exercise,
                form.cleaned_data,
            )
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Set added.")
    else:
        messages.error(request, _first_form_error(form))
    return redirect("session_detail", pk=session.pk)


def set_row(request, pk):
    set_log = _get_set_log(request.user, pk)
    return render(request, "workouts/_set_row.html", {"set_log": set_log, "editable": True})


def set_edit(request, pk):
    set_log = _get_set_log(request.user, pk)
    tracking_type = set_log.session_exercise.exercise.tracking_type
    if request.method == "POST":
        form = SetLogForm(request.POST, tracking_type=tracking_type)
        if form.is_valid():
            try:
                session_services.update_manual_set(request.user, set_log, form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, "Set saved.")
                if _is_row_request(request, set_log):
                    return render(
                        request,
                        "workouts/_set_row_swap.html",
                        {"set_log": set_log},
                    )
                return redirect("session_detail", pk=set_log.session_exercise.session_id)
        if _is_row_request(request, set_log):
            return render(
                request,
                "workouts/_set_row_edit.html",
                {"set_log": set_log, "form": form},
            )
    else:
        form = SetLogForm(
            tracking_type=tracking_type,
            initial=_set_initial(set_log),
        )
        if _is_row_request(request, set_log):
            return render(
                request,
                "workouts/_set_row_edit.html",
                {"set_log": set_log, "form": form},
            )

    return render(
        request,
        "workouts/set_form.html",
        {
            "page_title": "Edit set",
            "session": set_log.session_exercise.session,
            "set_log": set_log,
            "form": form,
        },
    )


def set_delete(request, pk):
    set_log = _get_set_log(request.user, pk)
    session = set_log.session_exercise.session
    if request.method == "POST" and request.POST.get("confirm") == "1":
        try:
            session_services.delete_manual_set(request.user, set_log)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(request, "Set deleted.")
        return redirect("session_detail", pk=session.pk)
    return render(
        request,
        "plans/confirm.html",
        {
            "page_title": "Delete set?",
            "confirm_title": "Delete set?",
            "confirm_message": (
                f"Delete set {set_log.set_number} of "
                f"{set_log.session_exercise.exercise.name}? "
                "The remaining set numbers close the gap."
            ),
            "confirm_label": "Delete set",
            "cancel_href": reverse("session_detail", args=[session.pk]),
        },
    )


# --- Tags -------------------------------------------------------------------


def tag_new(request):
    """Create a tag from Settings."""
    if request.method == "POST":
        form = TagForm(request.POST, user=request.user)
        if form.is_valid():
            tag = tag_services.create_tag(
                request.user,
                name=form.cleaned_data["name"],
                color=form.cleaned_data["color"],
            )
            messages.success(request, f"Added {tag.name}.")
            return redirect("settings")
    else:
        form = TagForm(user=request.user, initial={"color": tag_services.DEFAULT_TAG_COLOR})
    return render(
        request,
        "workouts/tag_form.html",
        {"page_title": "New tag", "form": form, "tag": None},
    )


def tag_edit(request, pk):
    """Rename or recolor a tag."""
    tag = tag_services.get_tag(request.user, pk)
    if request.method == "POST":
        form = TagForm(request.POST, user=request.user, tag=tag)
        if form.is_valid():
            tag_services.update_tag(
                request.user,
                tag,
                name=form.cleaned_data["name"],
                color=form.cleaned_data["color"],
            )
            messages.success(request, "Tag updated.")
            return redirect("settings")
    else:
        form = TagForm(user=request.user, tag=tag, initial={"name": tag.name, "color": tag.color})
    return render(
        request,
        "workouts/tag_form.html",
        {"page_title": "Edit tag", "form": form, "tag": tag},
    )


def tag_delete(request, pk):
    tag = tag_services.get_tag(request.user, pk)
    if request.method == "POST" and request.POST.get("confirm") == "1":
        tag_services.delete_tag(request.user, tag)
        messages.success(request, "Tag deleted.")
        return redirect("settings")
    return render(
        request,
        "plans/confirm.html",
        {
            "page_title": "Delete tag?",
            "confirm_title": "Delete tag?",
            "confirm_message": (
                f"Delete {tag.name}? It is removed from every workout and from your default tags."
            ),
            "confirm_label": "Delete tag",
            "cancel_href": reverse("settings"),
        },
    )


# --- History ----------------------------------------------------------------


def _tag_filter(user, raw):
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return None
    return Tag.objects.filter(user=user, pk=pk).first()


def _plan_filter(user, raw):
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return None
    return Plan.objects.for_user(user).filter(pk=pk).first()


def _month_parts(raw, today):
    if raw:
        try:
            parsed = date.fromisoformat(f"{raw}-01")
            return parsed.year, parsed.month
        except ValueError:
            pass
    return today.year, today.month


def _query_string(request, **overrides) -> str:
    """Keep the current filters while changing a view, month, or day."""
    params = request.GET.copy()
    for key, value in overrides.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = str(value)
    return params.urlencode()


def _add_history_links(request, context):
    """Add ready-to-use URLs so the template stays free of query building."""
    context["calendar_url"] = "?" + _query_string(request, view="calendar", day=None)
    context["list_url"] = "?" + _query_string(request, view="list", day=None)
    if context["view"] == "calendar":
        context["prev_url"] = "?" + _query_string(
            request, view="calendar", month=context["prev_month"], day=None
        )
        context["next_url"] = "?" + _query_string(
            request, view="calendar", month=context["next_month"], day=None
        )
        for week in context["weeks"]:
            for day in week:
                day["url"] = "?" + _query_string(
                    request,
                    view="calendar",
                    month=day["date"].strftime("%Y-%m"),
                    day=day["date"].isoformat(),
                )
    return context


def history_view(request):
    """Calendar or list history with tag and plan filters (F-09)."""
    today = timezone.localdate()
    view = request.GET.get("view", "calendar")
    if view not in ("calendar", "list"):
        view = "calendar"
    year, month = _month_parts(request.GET.get("month", ""), today)
    context = history.build_history(
        request.user,
        view=view,
        year=year,
        month=month,
        tag=_tag_filter(request.user, request.GET.get("tag")),
        exclude_tag=_tag_filter(request.user, request.GET.get("exclude_tag")),
        plan=_plan_filter(request.user, request.GET.get("plan")),
        selected_day=request.GET.get("day"),
        today=today,
    )
    context.update({"page_title": "History", "today": today})
    context = _add_history_links(request, context)
    return render(request, "workouts/history.html", context)
