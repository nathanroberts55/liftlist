from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_healthz_is_public_and_checks_the_database(client):
    response = client.get("/healthz/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.django_db
def test_healthz_returns_503_when_the_database_is_unavailable(client):
    with patch("apps.core.views.connection") as connection:
        connection.cursor.side_effect = RuntimeError("database down")
        response = client.get("/healthz/")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}


@pytest.mark.django_db
def test_healthz_is_not_cached(client):
    response = client.get("/healthz/")

    assert response["Cache-Control"] == "max-age=0, no-cache, no-store, must-revalidate, private"
