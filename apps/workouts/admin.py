from django.contrib import admin

from .models import Session, SessionExercise, SetLog, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "color")
    list_select_related = ("user",)
    search_fields = ("name", "user__username")


class SetLogInline(admin.TabularInline):
    model = SetLog
    extra = 0
    fields = (
        "set_number",
        "status",
        "weight_lb",
        "reps",
        "duration_seconds",
        "distance_m",
        "difficulty",
        "is_extra",
    )


class SessionExerciseInline(admin.TabularInline):
    model = SessionExercise
    extra = 0
    fields = (
        "order",
        "exercise",
        "superset_group",
        "target_sets",
        "planned_sets",
        "status",
    )


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "performed_date", "status", "kind")
    list_filter = ("status", "kind")
    list_select_related = ("user", "plan_day")
    search_fields = ("title", "user__username")
    date_hierarchy = "performed_date"
    filter_horizontal = ("tags",)
    inlines = (SessionExerciseInline,)


@admin.register(SessionExercise)
class SessionExerciseAdmin(admin.ModelAdmin):
    list_display = ("exercise", "session", "order", "superset_group", "status")
    list_filter = ("status",)
    list_select_related = ("exercise", "session")
    search_fields = ("exercise__name", "session__title", "session__user__username")
    inlines = (SetLogInline,)


@admin.register(SetLog)
class SetLogAdmin(admin.ModelAdmin):
    list_display = ("session_exercise", "set_number", "status", "weight_lb", "reps")
    list_filter = ("status",)
    list_select_related = ("session_exercise", "session_exercise__session")
    search_fields = (
        "session_exercise__exercise__name",
        "session_exercise__session__title",
    )
