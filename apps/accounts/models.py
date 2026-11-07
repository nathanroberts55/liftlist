"""Per-user preferences."""

from django.conf import settings
from django.db import models


class UserSettings(models.Model):
    """Preferences for one user. Created automatically with the user."""

    class Theme(models.TextChoices):
        DARK = "DARK", "Dark"
        LIGHT = "LIGHT", "Light"
        SYSTEM = "SYSTEM", "Match device"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    theme = models.CharField(max_length=10, choices=Theme.choices, default=Theme.DARK)
    default_rest_seconds = models.PositiveSmallIntegerField(default=90)
    timer_sound = models.BooleanField(default=True)
    default_tags = models.ManyToManyField(
        "workouts.Tag",
        blank=True,
        related_name="default_for_settings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user settings"
        verbose_name_plural = "user settings"

    def __str__(self) -> str:
        return f"Settings for {self.user}"
