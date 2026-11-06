from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse


@pytest.mark.django_db
def test_manifest_is_public(client):
    response = client.get(reverse("manifest"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/manifest+json")


@pytest.mark.django_db
def test_manifest_is_installable(client):
    data = client.get(reverse("manifest")).json()

    assert data["name"] == "Lift List"
    assert data["short_name"] == "Lift List"
    assert data["start_url"] == "/"
    assert data["display"] == "standalone"
    assert data["theme_color"] == "#0B0D10"

    purposes = {icon["purpose"] for icon in data["icons"]}
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert {"any", "maskable"} <= purposes
    assert {"192x192", "512x512"} <= sizes


@pytest.mark.django_db
def test_manifest_icons_exist_on_disk(client):
    data = client.get(reverse("manifest")).json()
    static_root = Path(settings.STATICFILES_DIRS[0])

    for icon in data["icons"]:
        path = static_root / icon["src"].removeprefix(settings.STATIC_URL)
        assert path.is_file(), f"Missing icon: {path}"


@pytest.mark.django_db
def test_apple_touch_icon_exists():
    path = Path(settings.STATICFILES_DIRS[0]) / "img" / "icons" / "apple-touch-icon.png"

    assert path.is_file()
