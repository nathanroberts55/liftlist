import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import UserSettings
from apps.accounts.services.settings import get_settings, update_theme


@pytest.mark.django_db
def test_get_settings_returns_the_existing_record(user):
    existing = user.settings

    assert get_settings(user) == existing


@pytest.mark.django_db
def test_get_settings_recreates_a_missing_record(user):
    UserSettings.objects.filter(user=user).delete()

    user_settings = get_settings(user)

    assert user_settings.pk is not None
    assert user_settings.theme == UserSettings.Theme.DARK


@pytest.mark.django_db
def test_update_theme_persists_the_choice(user):
    updated = update_theme(user, UserSettings.Theme.LIGHT)

    user.settings.refresh_from_db()
    assert updated.pk == user.settings.pk
    assert user.settings.theme == UserSettings.Theme.LIGHT


@pytest.mark.django_db
def test_update_theme_rejects_an_unknown_theme(user):
    with pytest.raises(ValidationError):
        update_theme(user, "PURPLE")

    user.settings.refresh_from_db()
    assert user.settings.theme == UserSettings.Theme.DARK


@pytest.mark.django_db
def test_update_theme_only_touches_the_given_user(user, other_user):
    update_theme(user, UserSettings.Theme.LIGHT)

    other_user.settings.refresh_from_db()
    assert other_user.settings.theme == UserSettings.Theme.DARK
