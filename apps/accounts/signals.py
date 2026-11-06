"""Signals that keep per-user records in sync."""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserSettings


@receiver(
    post_save,
    sender=settings.AUTH_USER_MODEL,
    dispatch_uid="accounts.create_user_settings",
)
def create_user_settings(sender, instance, created, **kwargs):
    """Create UserSettings for every new user (including createsuperuser)."""
    if created:
        UserSettings.objects.get_or_create(user=instance)
