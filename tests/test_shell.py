import pytest
from django.urls import reverse
from freezegun import freeze_time


@pytest.mark.django_db
def test_authenticated_user_sees_the_app_shell(client, user):
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert b"No active plan" in response.content
    for label in (b"Today", b"Plan", b"Library", b"History", b"Stats"):
        assert label in response.content


@pytest.mark.django_db
def test_stats_is_no_longer_a_placeholder(client, user):
    client.force_login(user)

    response = client.get(reverse("stats"))

    assert response.status_code == 200
    assert b"Progress charts are coming" not in response.content
    assert b"Weight over time" in response.content
    assert b"No weight history yet" in response.content


@pytest.mark.django_db
def test_history_is_no_longer_a_placeholder(client, user):
    client.force_login(user)

    response = client.get(reverse("history"))

    assert response.status_code == 200
    assert b"Workout history is coming" not in response.content
    assert b"History" in response.content
    assert b"Nothing recorded for this day." in response.content


@pytest.mark.django_db
def test_plans_is_no_longer_a_placeholder(client, user):
    client.force_login(user)

    response = client.get(reverse("plans"))

    assert response.status_code == 200
    assert b"The plan builder is coming" not in response.content
    assert b"No plans yet" in response.content


@pytest.mark.django_db
def test_library_is_no_longer_a_placeholder(client, user):
    client.force_login(user)

    response = client.get(reverse("library"))

    assert response.status_code == 200
    assert b"The exercise library is coming" not in response.content
    assert b"Search exercises" in response.content


@pytest.mark.django_db
@freeze_time("2026-11-09 12:00:00")
def test_today_shows_the_local_date(client, user):
    client.force_login(user)

    response = client.get(reverse("today"))

    assert response.status_code == 200
    assert b"Mon, Nov 9" in response.content


@pytest.mark.django_db
def test_authenticated_page_has_install_metadata(client, user):
    client.force_login(user)

    response = client.get(reverse("today"))

    assert b'rel="manifest"' in response.content
    assert b"apple-touch-icon" in response.content
    assert b"apple-mobile-web-app-capable" in response.content


@pytest.mark.django_db
def test_authenticated_pages_boost_navigation(client, user):
    client.force_login(user)

    response = client.get(reverse("today"))

    assert b'hx-boost="true"' in response.content


@pytest.mark.django_db
def test_login_page_is_not_boosted(client):
    response = client.get(reverse("login"))

    assert b'hx-boost="true"' not in response.content


@pytest.mark.django_db
def test_logout_form_is_not_boosted(client, user):
    client.force_login(user)

    response = client.get(reverse("today"))

    assert f'action="{reverse("logout")}" hx-boost="false"'.encode() in response.content


@pytest.mark.django_db
def test_authenticated_pages_load_the_htmx_scripts(client, user):
    client.force_login(user)

    response = client.get(reverse("today"))

    assert b"vendor/sortable.min.js" in response.content
    assert b"js/plan-reorder.js" in response.content
    assert b"js/htmx-focus.js" in response.content


@pytest.mark.django_db
def test_login_page_does_not_load_the_htmx_scripts(client):
    response = client.get(reverse("login"))

    assert b"js/plan-reorder.js" not in response.content
    assert b"js/htmx-focus.js" not in response.content
