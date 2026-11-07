import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.models import UserSettings


@pytest.mark.django_db
def test_settings_are_created_with_the_user(user):
    assert user.settings.theme == UserSettings.Theme.DARK
    assert user.settings.default_rest_seconds == 90


@pytest.mark.django_db
def test_settings_are_created_for_superusers():
    admin = get_user_model().objects.create_superuser(
        username="admin", email="admin@example.com", password="correct-horse-battery"
    )

    assert admin.settings.theme == UserSettings.Theme.DARK


@pytest.mark.django_db
def test_settings_page_requires_login(client):
    response = client.get(reverse("settings"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_settings_page_lists_all_themes(client, user):
    client.force_login(user)

    response = client.get(reverse("settings"))

    assert response.status_code == 200
    assert b"Dark" in response.content
    assert b"Light" in response.content
    assert b"Match device" in response.content


@pytest.mark.django_db
def test_posting_a_theme_updates_only_the_current_user(client, user, other_user):
    client.force_login(user)

    response = client.post(
        reverse("settings"),
        {"theme": UserSettings.Theme.LIGHT, "default_rest_seconds": 90},
    )

    assert response.status_code == 302
    user.settings.refresh_from_db()
    other_user.settings.refresh_from_db()
    assert user.settings.theme == UserSettings.Theme.LIGHT
    assert other_user.settings.theme == UserSettings.Theme.DARK


@pytest.mark.django_db
def test_invalid_theme_is_rejected(client, user):
    client.force_login(user)

    response = client.post(
        reverse("settings"),
        {"theme": "PURPLE", "default_rest_seconds": 90},
    )

    assert response.status_code == 200
    user.settings.refresh_from_db()
    assert user.settings.theme == UserSettings.Theme.DARK


@pytest.mark.django_db
def test_default_rest_is_saved(client, user):
    client.force_login(user)

    response = client.post(
        reverse("settings"),
        {"theme": UserSettings.Theme.DARK, "default_rest_seconds": 120},
    )

    assert response.status_code == 302
    user.settings.refresh_from_db()
    assert user.settings.default_rest_seconds == 120


@pytest.mark.django_db
def test_default_rest_is_capped_at_one_hour(client, user):
    client.force_login(user)

    response = client.post(
        reverse("settings"),
        {"theme": UserSettings.Theme.DARK, "default_rest_seconds": 3601},
    )

    assert response.status_code == 200
    user.settings.refresh_from_db()
    assert user.settings.default_rest_seconds == 90


@pytest.mark.django_db
def test_timer_sound_preference_is_saved(client, user):
    client.force_login(user)

    response = client.post(
        reverse("settings"),
        {
            "theme": UserSettings.Theme.DARK,
            "default_rest_seconds": 90,
            "timer_sound": "on",
        },
    )

    assert response.status_code == 302
    user.settings.refresh_from_db()
    assert user.settings.timer_sound is True

    client.post(
        reverse("settings"),
        {"theme": UserSettings.Theme.DARK, "default_rest_seconds": 90},
    )

    user.settings.refresh_from_db()
    assert user.settings.timer_sound is False


@pytest.mark.django_db
def test_light_theme_is_applied_server_side(client, user):
    user.settings.theme = UserSettings.Theme.LIGHT
    user.settings.save()
    client.force_login(user)

    response = client.get(reverse("today"))

    assert b'data-theme="liftlist-light"' in response.content
    assert b'name="theme-color" content="#F5F6F8"' in response.content


@pytest.mark.django_db
def test_system_theme_uses_device_preference_before_paint(client, user):
    user.settings.theme = UserSettings.Theme.SYSTEM
    user.settings.save()
    client.force_login(user)

    response = client.get(reverse("today"))

    assert b'data-theme="liftlist-dark"' in response.content
    assert b"prefers-color-scheme" in response.content
    # The script must run after the meta tag it updates exists.
    assert response.content.index(b'name="theme-color"') < response.content.index(
        b"prefers-color-scheme"
    )


@pytest.mark.django_db
def test_theme_context_processor_tolerates_missing_settings(user):
    UserSettings.objects.filter(user=user).delete()

    from apps.accounts.context_processors import theme

    request = type("Request", (), {"user": user})()
    context = theme(request)

    assert context["theme"] == "liftlist-dark"
