"""Account services: settings lookup and updates."""

from django.db import transaction

from ..models import UserSettings


def get_settings(user) -> UserSettings:
    """Return the user's settings, creating them if they are missing."""
    user_settings, _ = UserSettings.objects.get_or_create(user=user)
    return user_settings


def update_theme(user, theme: str) -> UserSettings:
    """Validate and persist the user's theme preference."""
    user_settings = get_settings(user)
    user_settings.theme = theme
    user_settings.full_clean()
    user_settings.save(update_fields=["theme", "updated_at"])
    return user_settings


@transaction.atomic
def update_preferences(
    user,
    *,
    theme: str,
    default_rest_seconds: int,
    timer_sound: bool = True,
    default_tag_ids=(),
) -> UserSettings:
    """Persist the settings shown on the Settings screen."""
    user_settings = get_settings(user)
    user_settings.theme = theme
    user_settings.default_rest_seconds = default_rest_seconds
    user_settings.timer_sound = timer_sound
    user_settings.full_clean()
    user_settings.save(
        update_fields=[
            "theme",
            "default_rest_seconds",
            "timer_sound",
            "updated_at",
        ]
    )
    from apps.workouts.models import Tag

    user_settings.default_tags.set(Tag.objects.filter(user=user, pk__in=default_tag_ids))
    return user_settings
