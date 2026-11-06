from django.contrib import admin

from .models import Exercise, ExerciseArchive, MuscleGroup


@admin.register(MuscleGroup)
class MuscleGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "display_order")
    ordering = ("display_order", "name")
    search_fields = ("name",)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "primary_muscle",
        "tracking_type",
        "is_archived",
    )
    list_filter = ("primary_muscle", "tracking_type", "is_archived")
    list_select_related = ("user", "primary_muscle")
    search_fields = ("name", "user__username")
    filter_horizontal = ("secondary_muscles",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "user",
                    "name",
                    "primary_muscle",
                    "secondary_muscles",
                    "tracking_type",
                    "notes",
                    "is_archived",
                ),
                "description": (
                    "Leave user empty for a seeded/global exercise. Seeded rows "
                    "are archived per user through ExerciseArchive."
                ),
            },
        ),
    )


@admin.register(ExerciseArchive)
class ExerciseArchiveAdmin(admin.ModelAdmin):
    list_display = ("exercise", "user", "created_at")
    list_select_related = ("exercise", "user")
    search_fields = ("exercise__name", "user__username")
