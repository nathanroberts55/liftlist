from django.contrib import admin

from .models import UserSettings


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "theme", "timer_sound", "updated_at")
    list_select_related = ("user",)
    search_fields = ("user__username",)
    filter_horizontal = ("default_tags",)
