import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.workouts.models import Tag
from apps.workouts.services import tags as tag_services


def _tag(user, name="PT", color=tag_services.DEFAULT_TAG_COLOR):
    return Tag.objects.create(user=user, name=name, color=color)


@pytest.mark.django_db
def test_create_tag_persists_the_name_and_color(user):
    tag = tag_services.create_tag(user, name="  PT  ", color="#30D158")

    assert tag.pk is not None
    assert tag.name == "PT"
    assert tag.color == "#30D158"
    assert tag.user == user


@pytest.mark.django_db
def test_create_tag_rejects_a_duplicate_name_ignoring_case(user):
    _tag(user, name="PT")

    with pytest.raises(ValidationError):
        tag_services.create_tag(user, name="pt", color=tag_services.DEFAULT_TAG_COLOR)

    assert Tag.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_create_tag_rejects_a_color_outside_the_palette(user):
    with pytest.raises(ValidationError):
        tag_services.create_tag(user, name="PT", color="#123456")


@pytest.mark.django_db
def test_list_tags_counts_sessions_per_tag(user, seeded_exercise):
    from datetime import date

    from apps.workouts.models import Session

    tag = _tag(user)
    session = Session.objects.create(
        user=user,
        title="Push day",
        performed_date=date(2026, 11, 9),
        status=Session.Status.COMPLETED,
    )
    session.tags.set([tag])

    listed = list(tag_services.list_tags(user))

    assert listed == [tag]
    assert listed[0].session_count == 1


@pytest.mark.django_db
def test_update_tag_renames_and_recolors(user):
    tag = _tag(user)

    updated = tag_services.update_tag(user, tag, name="Physical therapy", color="#BF5AF2")

    updated.refresh_from_db()
    assert updated.name == "Physical therapy"
    assert updated.color == "#BF5AF2"


@pytest.mark.django_db
def test_update_tag_rejects_another_users_tag(user, other_user):
    tag = _tag(other_user)

    with pytest.raises(ValidationError):
        tag_services.update_tag(user, tag, name="PT", color="#30D158")


@pytest.mark.django_db
def test_delete_tag_removes_it(user):
    tag = _tag(user)

    tag_services.delete_tag(user, tag)

    assert not Tag.objects.filter(pk=tag.pk).exists()


@pytest.mark.django_db
def test_delete_tag_rejects_another_users_tag(user, other_user):
    tag = _tag(other_user)

    with pytest.raises(ValidationError):
        tag_services.delete_tag(user, tag)

    assert Tag.objects.filter(pk=tag.pk).exists()


@pytest.mark.django_db
def test_resolve_tags_rejects_another_users_tag(user, other_user):
    own = _tag(user, name="PT")
    foreign = _tag(other_user, name="HIIT")

    with pytest.raises(ValidationError):
        tag_services.resolve_tags(user, [own.pk, foreign.pk])


@pytest.mark.django_db
def test_default_tags_round_trip(user):
    first = _tag(user, name="PT")
    second = _tag(user, name="HIIT")

    tag_services.set_default_tags(user, [second.pk, first.pk])

    assert tag_services.default_tags(user) == [second, first]


@pytest.mark.django_db
def test_default_tags_are_scoped_to_the_user(user, other_user):
    other = _tag(other_user, name="PT")

    assert tag_services.default_tags(user) == []

    tag_services.set_default_tags(other_user, [other.pk])

    assert tag_services.default_tags(user) == []
    assert tag_services.default_tags(other_user) == [other]


@pytest.mark.django_db
def test_tag_routes_require_login(client):
    urls = [
        ("get", reverse("tag_new")),
        ("post", reverse("tag_new")),
        ("get", reverse("tag_edit", args=[1])),
        ("post", reverse("tag_edit", args=[1])),
        ("get", reverse("tag_delete", args=[1])),
        ("post", reverse("tag_delete", args=[1])),
    ]
    for method, url in urls:
        response = getattr(client, method)(url)
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))


@pytest.mark.django_db
def test_new_tag_page_renders_the_palette(client, user):
    client.force_login(user)

    response = client.get(reverse("tag_new"))

    assert response.status_code == 200
    assert b"New tag" in response.content
    assert b"Blue" in response.content
    assert b"Gray" in response.content


@pytest.mark.django_db
def test_new_tag_post_creates_and_returns_to_settings(client, user):
    client.force_login(user)

    response = client.post(
        reverse("tag_new"),
        {"name": "PT", "color": tag_services.DEFAULT_TAG_COLOR},
    )

    assert response.status_code == 302
    assert response.url == reverse("settings")
    tag = Tag.objects.get(user=user, name="PT")
    assert tag.color == tag_services.DEFAULT_TAG_COLOR


@pytest.mark.django_db
def test_new_tag_post_rejects_a_duplicate(client, user):
    _tag(user, name="PT")
    client.force_login(user)

    response = client.post(
        reverse("tag_new"),
        {"name": "pt", "color": tag_services.DEFAULT_TAG_COLOR},
    )

    assert response.status_code == 200
    assert b"You already have a tag with that name." in response.content
    assert Tag.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_edit_tag_page_prefills_the_tag(client, user):
    tag = _tag(user, name="PT", color="#30D158")
    client.force_login(user)

    response = client.get(reverse("tag_edit", args=[tag.pk]))

    assert response.status_code == 200
    assert b'value="PT"' in response.content
    assert b'value="#30D158"' in response.content
    assert b"checked" in response.content


@pytest.mark.django_db
def test_edit_tag_post_updates_and_returns_to_settings(client, user):
    tag = _tag(user)
    client.force_login(user)

    response = client.post(
        reverse("tag_edit", args=[tag.pk]),
        {"name": "Physical therapy", "color": "#BF5AF2"},
    )

    assert response.status_code == 302
    assert response.url == reverse("settings")
    tag.refresh_from_db()
    assert tag.name == "Physical therapy"
    assert tag.color == "#BF5AF2"


@pytest.mark.django_db
def test_cannot_edit_another_users_tag(client, user, other_user):
    tag = _tag(other_user)
    client.force_login(user)

    response = client.get(reverse("tag_edit", args=[tag.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_tag_page_asks_for_confirmation(client, user):
    tag = _tag(user)
    client.force_login(user)

    response = client.get(reverse("tag_delete", args=[tag.pk]))

    assert response.status_code == 200
    assert b"Delete tag?" in response.content
    assert Tag.objects.filter(pk=tag.pk).exists()


@pytest.mark.django_db
def test_delete_tag_post_removes_it(client, user):
    tag = _tag(user)
    client.force_login(user)

    response = client.post(reverse("tag_delete", args=[tag.pk]), {"confirm": "1"})

    assert response.status_code == 302
    assert response.url == reverse("settings")
    assert not Tag.objects.filter(pk=tag.pk).exists()


@pytest.mark.django_db
def test_cannot_delete_another_users_tag(client, user, other_user):
    tag = _tag(other_user)
    client.force_login(user)

    response = client.post(reverse("tag_delete", args=[tag.pk]), {"confirm": "1"})

    assert response.status_code == 404
    assert Tag.objects.filter(pk=tag.pk).exists()


@pytest.mark.django_db
def test_settings_shows_tags_with_their_workout_count(client, user, seeded_exercise):
    from datetime import date

    from apps.workouts.models import Session

    tag = _tag(user, name="PT")
    session = Session.objects.create(
        user=user,
        title="Push day",
        performed_date=date(2026, 11, 9),
        status=Session.Status.COMPLETED,
    )
    session.tags.set([tag])
    client.force_login(user)

    response = client.get(reverse("settings"))

    content = response.content.decode()
    assert "PT" in content
    assert "1 workout" in content
    assert reverse("tag_edit", args=[tag.pk]) in content
    assert reverse("tag_delete", args=[tag.pk]) in content


@pytest.mark.django_db
def test_settings_does_not_show_another_users_tags(client, user, other_user):
    _tag(other_user, name="Secret tag")
    client.force_login(user)

    response = client.get(reverse("settings"))

    assert b"Secret tag" not in response.content
