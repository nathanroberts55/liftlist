from django.contrib import admin

from .models import Plan, PlanDay, PlanItem, ScheduledWorkout


class PlanDayInline(admin.TabularInline):
    model = PlanDay
    extra = 0
    fields = ("name", "weekday", "order", "focus_muscles")
    filter_horizontal = ("focus_muscles",)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "split_type", "start_date", "length_weeks", "status")
    list_filter = ("status", "split_type")
    list_select_related = ("user",)
    search_fields = ("name", "user__username")
    inlines = (PlanDayInline,)


class PlanItemInline(admin.TabularInline):
    model = PlanItem
    extra = 0
    fields = (
        "order",
        "exercise",
        "superset_group",
        "target_sets",
        "rep_min",
        "rep_max",
        "target_seconds",
        "target_distance_m",
        "distance_unit",
        "rest_seconds",
    )


@admin.register(PlanDay)
class PlanDayAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "weekday", "order")
    list_filter = ("weekday", "plan__status")
    list_select_related = ("plan", "plan__user")
    search_fields = ("name", "plan__name", "plan__user__username")
    filter_horizontal = ("focus_muscles",)
    inlines = (PlanItemInline,)


@admin.register(PlanItem)
class PlanItemAdmin(admin.ModelAdmin):
    list_display = ("exercise", "plan_day", "order", "superset_group", "target_sets")
    list_filter = ("plan_day__plan__status",)
    list_select_related = ("exercise", "plan_day", "plan_day__plan")
    search_fields = ("exercise__name", "plan_day__name", "plan_day__plan__name")


@admin.register(ScheduledWorkout)
class ScheduledWorkoutAdmin(admin.ModelAdmin):
    list_display = ("plan_day", "scheduled_date", "status", "user", "plan")
    list_filter = ("status", "plan__status")
    list_select_related = ("user", "plan", "plan_day")
    search_fields = ("plan__name", "plan_day__name", "user__username")
    date_hierarchy = "scheduled_date"
