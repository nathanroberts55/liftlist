"""Workout runner views (F-05)."""

import uuid

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.exercises.models import Exercise
from apps.exercises.services.library import grouped_by_muscle, list_exercises
from apps.plans.models import ScheduledWorkout

from .models import Session, SessionExercise
from .services import progression, runner


def _get_session(user, pk) -> Session:
    return get_object_or_404(
        Session.objects.filter(user=user).select_related(
            "plan_day",
            "scheduled_workout",
            "scheduled_workout__plan_day",
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
