"""Exercise library views (F-02)."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.stats.services import aggregations as stats_aggregations
from apps.workouts.services import records as record_services

from .forms import ExerciseForm
from .models import Exercise, MuscleGroup
from .services.library import (
    archive_exercise,
    count_archived,
    create_exercise,
    get_exercise,
    grouped_by_muscle,
    is_archived_for,
    list_exercises,
    restore_exercise,
    update_exercise,
)


def library(request):
    """Grouped, searchable exercise list. Returns a partial for HTMX search."""
    query = request.GET.get("q", "").strip()
    muscle_slug = request.GET.get("muscle", "").strip()
    show_archived = request.GET.get("archived") == "1"

    exercises = list_exercises(
        user=request.user,
        query=query,
        muscle_slug=muscle_slug,
        archived=show_archived,
    )
    groups = grouped_by_muscle(exercises)
    context = {
        "page_title": "Library",
        "groups": groups,
        "muscles": MuscleGroup.objects.all(),
        "query": query,
        "muscle_slug": muscle_slug,
        "show_archived": show_archived,
        "archived_count": count_archived(request.user),
        "has_filters": bool(query or muscle_slug),
        "total_count": sum(len(group["exercises"]) for group in groups),
    }
    # Only the search form targets the list. Boosted page navigation is also an
    # HTMX request, so keying off request.htmx alone would replace the whole
    # document body with the fragment and strip the app shell.
    if request.htmx and request.headers.get("HX-Target") == "library-list":
        return render(request, "exercises/_list.html", context)
    return render(request, "exercises/library.html", context)


def detail(request, pk):
    """Exercise detail with records, recent sessions, and a weight chart."""
    exercise = get_exercise(request.user, pk)
    exercise_records = record_services.prs_for_exercise(request.user, exercise)
    chart = stats_aggregations.top_set_chart(request.user, exercise, "all")
    return render(
        request,
        "exercises/detail.html",
        {
            "page_title": exercise.name,
            "exercise": exercise,
            "is_archived": is_archived_for(request.user, exercise),
            "secondary_names": [muscle.name for muscle in exercise.secondary_muscles.all()],
            "records": exercise_records,
            "recent_sessions": stats_aggregations.recent_sessions(request.user, exercise),
            "chart": chart,
            "has_chart": bool(chart["labels"]),
        },
    )


def create(request):
    """Add a custom exercise."""
    if request.method == "POST":
        form = ExerciseForm(request.POST, user=request.user)
        if form.is_valid():
            exercise = create_exercise(user=request.user, **form.cleaned_data)
            messages.success(request, f"Added {exercise.name}.")
            return redirect("exercise_detail", pk=exercise.pk)
    else:
        form = ExerciseForm(
            user=request.user,
            initial={"tracking_type": Exercise.TrackingType.WEIGHT_REPS},
        )

    return render(
        request,
        "exercises/form.html",
        {
            "page_title": "New exercise",
            "form": form,
            "is_edit": False,
        },
    )


def edit(request, pk):
    """Edit a custom exercise. Seeded exercises can only be archived."""
    exercise = get_exercise(request.user, pk)
    if exercise.is_seeded:
        messages.error(
            request,
            "Seeded exercises can't be edited. You can archive it instead.",
        )
        return redirect("exercise_detail", pk=exercise.pk)

    if request.method == "POST":
        form = ExerciseForm(request.POST, user=request.user, exclude=exercise)
        if form.is_valid():
            update_exercise(
                user=request.user,
                exercise=exercise,
                **form.cleaned_data,
            )
            messages.success(request, "Exercise updated.")
            return redirect("exercise_detail", pk=exercise.pk)
    else:
        form = ExerciseForm(
            user=request.user,
            exclude=exercise,
            initial={
                "name": exercise.name,
                "primary_muscle": exercise.primary_muscle_id,
                "tracking_type": exercise.tracking_type,
                "default_distance_unit": exercise.default_distance_unit,
                "secondary_muscles": exercise.secondary_muscles.all(),
                "notes": exercise.notes,
            },
        )

    return render(
        request,
        "exercises/form.html",
        {
            "page_title": f"Edit {exercise.name}",
            "form": form,
            "exercise": exercise,
            "is_edit": True,
        },
    )


@require_POST
def archive(request, pk):
    """Hide an exercise for this user."""
    exercise = get_exercise(request.user, pk)
    archive_exercise(user=request.user, exercise=exercise)
    messages.success(request, f"Archived {exercise.name}.")
    return redirect("exercise_detail", pk=exercise.pk)


@require_POST
def restore(request, pk):
    """Undo an archive for this user."""
    exercise = get_exercise(request.user, pk)
    restore_exercise(user=request.user, exercise=exercise)
    messages.success(request, f"Restored {exercise.name}.")
    return redirect("exercise_detail", pk=exercise.pk)
