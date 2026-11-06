import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command


@pytest.fixture(autouse=True)
def clear_superuser_env(monkeypatch):
    for name in (
        "DJANGO_SUPERUSER_USERNAME",
        "DJANGO_SUPERUSER_PASSWORD",
        "DJANGO_SUPERUSER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.django_db
def test_noop_without_environment_variables():
    call_command("ensure_superuser")

    assert not get_user_model().objects.exists()


@pytest.mark.django_db
def test_creates_a_superuser_when_configured(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "admin")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "correct-horse-battery")
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")

    call_command("ensure_superuser")

    admin = get_user_model().objects.get(username="admin")
    assert admin.is_superuser
    assert admin.is_staff
    assert admin.email == "admin@example.com"
    assert admin.check_password("correct-horse-battery")


@pytest.mark.django_db
def test_is_idempotent(monkeypatch):
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "admin")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "correct-horse-battery")

    call_command("ensure_superuser")
    call_command("ensure_superuser")

    assert get_user_model().objects.filter(username="admin").count() == 1


@pytest.mark.django_db
def test_does_not_escalate_an_existing_user(monkeypatch):
    get_user_model().objects.create_user(username="admin", password="correct-horse-battery")
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "admin")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "another-password")

    call_command("ensure_superuser")

    admin = get_user_model().objects.get(username="admin")
    assert not admin.is_superuser
    assert admin.check_password("correct-horse-battery")
