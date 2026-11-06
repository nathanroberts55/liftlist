import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse

PROTECTED_PATHS = ["/", "/plans/", "/library/", "/history/", "/stats/", "/settings/"]


@pytest.mark.django_db
@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_anonymous_visitor_is_redirected_to_login(client, path):
    response = client.get(path)

    assert response.status_code == 302
    assert response.url.startswith(f"{reverse('login')}?next=")


@pytest.mark.django_db
def test_login_page_is_public(client):
    response = client.get(reverse("login"))

    assert response.status_code == 200
    assert b"ll-wordmark" in response.content


@pytest.mark.django_db
def test_login_with_valid_credentials_lands_on_today(client, user):
    response = client.post(
        reverse("login"),
        {"username": user.username, "password": "correct-horse-battery"},
    )

    assert response.status_code == 302
    assert response.url == reverse("today")


@pytest.mark.django_db
def test_login_honours_the_next_parameter(client, user):
    response = client.post(
        f"{reverse('login')}?next=/library/",
        {"username": user.username, "password": "correct-horse-battery", "next": "/library/"},
    )

    assert response.status_code == 302
    assert response.url == "/library/"


@pytest.mark.django_db
def test_login_with_invalid_credentials_shows_an_error(client, user):
    response = client.post(
        reverse("login"),
        {"username": user.username, "password": "wrong-password"},
    )

    assert response.status_code == 200
    assert b"Please enter a correct username and password" in response.content


@pytest.mark.django_db
def test_authenticated_user_is_redirected_away_from_login(client, user):
    client.force_login(user)

    response = client.get(reverse("login"))

    assert response.status_code == 302
    assert response.url == reverse("today")


@pytest.mark.django_db
def test_logout_requires_post_and_redirects_to_login(client, user):
    client.force_login(user)

    get_response = client.get(reverse("logout"))
    post_response = client.post(reverse("logout"))

    assert get_response.status_code == 405
    assert post_response.status_code == 302
    assert post_response.url == reverse("login")


@pytest.mark.django_db
def test_session_lasts_at_least_30_days():
    assert settings.SESSION_COOKIE_AGE >= 60 * 60 * 24 * 30


@pytest.mark.django_db
def test_no_sign_up_route(client):
    response = client.get("/signup/")

    assert response.status_code == 404


@pytest.mark.django_db
def test_superuser_login_works(client):
    user = get_user_model().objects.create_superuser(
        username="admin", email="admin@example.com", password="correct-horse-battery"
    )

    assert client.login(username=user.username, password="correct-horse-battery")
