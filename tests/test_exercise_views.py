import pytest
from django.urls import reverse

from apps.exercises.models import Exercise, ExerciseArchive


def make_custom(user, muscle, name="Cable Fly", **overrides):
    return Exercise.objects.create(
        user=user,
        name=name,
        primary_muscle=muscle,
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
        **overrides,
    )


# --- Access control ---------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("url_name", "kwargs"),
    [
        ("library", {}),
        ("exercise_new", {}),
        ("exercise_detail", {"pk": 1}),
        ("exercise_edit", {"pk": 1}),
        ("exercise_archive", {"pk": 1}),
        ("exercise_restore", {"pk": 1}),
    ],
)
def test_library_routes_require_login(client, url_name, kwargs):
    url = reverse(url_name, kwargs=kwargs)

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next={url}"


# --- Library list -----------------------------------------------------------


@pytest.mark.django_db
def test_library_groups_exercises_by_primary_muscle(client, user, muscles, seeded_exercise):
    client.force_login(user)

    response = client.get(reverse("library"))

    assert response.status_code == 200
    assert b"Barbell Bench Press" in response.content
    assert b'id="muscle-chest"' in response.content
    assert b"1 exercise" in response.content


@pytest.mark.django_db
def test_library_search_narrows_the_list(client, user, muscles):
    client.force_login(user)
    Exercise.objects.create(
        user=None,
        name="Bench Press",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    Exercise.objects.create(
        user=None,
        name="Back Squat",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )

    response = client.get(reverse("library"), {"q": "squat"})

    assert b"Back Squat" in response.content
    assert b"Bench Press" not in response.content


@pytest.mark.django_db
def test_library_muscle_filter_narrows_the_list(client, user, muscles):
    client.force_login(user)
    Exercise.objects.create(
        user=None,
        name="Bench Press",
        primary_muscle=muscles["Chest"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )
    Exercise.objects.create(
        user=None,
        name="Back Squat",
        primary_muscle=muscles["Quads"],
        tracking_type=Exercise.TrackingType.WEIGHT_REPS,
    )

    response = client.get(reverse("library"), {"muscle": "chest"})

    assert b"Bench Press" in response.content
    assert b"Back Squat" not in response.content


@pytest.mark.django_db
def test_library_returns_only_the_list_partial_for_the_search_target(
    client, user, muscles, seeded_exercise
):
    client.force_login(user)

    response = client.get(
        reverse("library"),
        {"q": "bench"},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="library-list",
    )

    assert response.status_code == 200
    assert b'id="library-list"' in response.content
    assert b"<html" not in response.content
    assert b"Barbell Bench Press" in response.content


@pytest.mark.django_db
def test_library_boosted_navigation_returns_the_full_page(client, user, seeded_exercise):
    """hx-boost sends HX-Request for normal nav clicks; the shell must survive."""
    client.force_login(user)

    response = client.get(
        reverse("library"),
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="body",
        HTTP_HX_BOOSTED="true",
    )

    assert response.status_code == 200
    assert b"<html" in response.content
    assert b'id="library-list"' in response.content
    assert b"<body" in response.content
    # Shell chrome: sidebar, topbar and bottom tab bar.
    assert b"ll-topbar" in response.content
    assert b"ll-tabbar" in response.content


@pytest.mark.django_db
def test_library_shows_the_empty_state_without_exercises(client, user):
    client.force_login(user)

    response = client.get(reverse("library"))

    assert b"No exercises yet" in response.content


@pytest.mark.django_db
def test_library_shows_no_matches_for_an_empty_search(client, user, seeded_exercise):
    client.force_login(user)

    response = client.get(reverse("library"), {"q": "zzzz"})

    assert b"No matches" in response.content


@pytest.mark.django_db
def test_library_archived_view_lists_archived_exercises(client, user, muscles, seeded_exercise):
    make_custom(user, muscles["Back"], name="Old Row", is_archived=True)
    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)
    client.force_login(user)

    response = client.get(reverse("library"), {"archived": "1"})

    assert response.status_code == 200
    assert b"Old Row" in response.content
    assert b"Barbell Bench Press" in response.content


@pytest.mark.django_db
def test_library_hides_another_users_custom_exercise(client, user, other_user, muscles):
    make_custom(other_user, muscles["Chest"], name="Their Secret Move")
    client.force_login(user)

    response = client.get(reverse("library"))

    assert b"Their Secret Move" not in response.content


# --- Detail -----------------------------------------------------------------


@pytest.mark.django_db
def test_detail_shows_a_seeded_exercise_without_an_edit_link(client, user, seeded_exercise):
    client.force_login(user)

    response = client.get(reverse("exercise_detail", kwargs={"pk": seeded_exercise.pk}))

    assert response.status_code == 200
    assert b"Barbell Bench Press" in response.content
    assert b"Seeded" in response.content
    assert reverse("exercise_edit", kwargs={"pk": seeded_exercise.pk}).encode() not in (
        response.content
    )


@pytest.mark.django_db
def test_detail_offers_edit_and_archive_to_the_owner(client, user, custom_exercise):
    client.force_login(user)

    response = client.get(reverse("exercise_detail", kwargs={"pk": custom_exercise.pk}))

    assert reverse("exercise_edit", kwargs={"pk": custom_exercise.pk}).encode() in (
        response.content
    )
    assert reverse("exercise_archive", kwargs={"pk": custom_exercise.pk}).encode() in (
        response.content
    )


@pytest.mark.django_db
def test_detail_offers_restore_when_archived(client, user, seeded_exercise):
    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)
    client.force_login(user)

    response = client.get(reverse("exercise_detail", kwargs={"pk": seeded_exercise.pk}))

    assert b"Restore exercise" in response.content
    assert b"Archived" in response.content


@pytest.mark.django_db
def test_detail_returns_404_for_another_users_custom_exercise(client, user, other_user, muscles):
    theirs = make_custom(other_user, muscles["Chest"])
    client.force_login(user)

    response = client.get(reverse("exercise_detail", kwargs={"pk": theirs.pk}))

    assert response.status_code == 404


# --- Create -----------------------------------------------------------------


@pytest.mark.django_db
def test_create_page_renders_the_form(client, user):
    client.force_login(user)

    response = client.get(reverse("exercise_new"))

    assert response.status_code == 200
    assert b"New exercise" in response.content
    for muscle in ("Chest", "Back", "Quads", "Cardio"):
        assert muscle.encode() in response.content


@pytest.mark.django_db
def test_create_saves_a_custom_exercise_for_the_user(client, user, muscles):
    client.force_login(user)

    response = client.post(
        reverse("exercise_new"),
        {
            "name": "Landmine Press",
            "primary_muscle": muscles["Shoulders"].pk,
            "tracking_type": Exercise.TrackingType.BODYWEIGHT,
            "secondary_muscles": [muscles["Triceps"].pk],
            "notes": "Half-kneeling",
        },
    )

    exercise = Exercise.objects.get(user=user, name="Landmine Press")
    assert response.status_code == 302
    assert response.url == reverse("exercise_detail", kwargs={"pk": exercise.pk})
    assert exercise.primary_muscle == muscles["Shoulders"]
    assert exercise.tracking_type == Exercise.TrackingType.BODYWEIGHT
    assert list(exercise.secondary_muscles.all()) == [muscles["Triceps"]]


@pytest.mark.django_db
def test_create_rejects_a_duplicate_seeded_name(client, user, muscles, seeded_exercise):
    client.force_login(user)

    response = client.post(
        reverse("exercise_new"),
        {
            "name": "barbell bench press",
            "primary_muscle": muscles["Chest"].pk,
            "tracking_type": Exercise.TrackingType.WEIGHT_REPS,
        },
    )

    assert response.status_code == 200
    assert b"already exists" in response.content
    assert not Exercise.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_create_rejects_a_primary_muscle_listed_as_secondary(client, user, muscles):
    client.force_login(user)

    response = client.post(
        reverse("exercise_new"),
        {
            "name": "Broken Move",
            "primary_muscle": muscles["Chest"].pk,
            "tracking_type": Exercise.TrackingType.WEIGHT_REPS,
            "secondary_muscles": [muscles["Chest"].pk],
        },
    )

    assert response.status_code == 200
    assert b"can&#x27;t also be a secondary muscle" in response.content
    assert not Exercise.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_create_requires_a_name(client, user, muscles):
    client.force_login(user)

    response = client.post(
        reverse("exercise_new"),
        {
            "name": "   ",
            "primary_muscle": muscles["Chest"].pk,
            "tracking_type": Exercise.TrackingType.WEIGHT_REPS,
        },
    )

    assert response.status_code == 200
    assert b"Enter an exercise name." in response.content


# --- Edit -------------------------------------------------------------------


@pytest.mark.django_db
def test_edit_updates_a_custom_exercise(client, user, custom_exercise):
    client.force_login(user)

    response = client.post(
        reverse("exercise_edit", kwargs={"pk": custom_exercise.pk}),
        {
            "name": "Low Cable Fly",
            "primary_muscle": custom_exercise.primary_muscle.pk,
            "tracking_type": Exercise.TrackingType.TIMED,
            "notes": "Slow eccentric",
        },
    )

    custom_exercise.refresh_from_db()
    assert response.status_code == 302
    assert custom_exercise.name == "Low Cable Fly"
    assert custom_exercise.tracking_type == Exercise.TrackingType.TIMED
    assert custom_exercise.notes == "Slow eccentric"


@pytest.mark.django_db
def test_edit_redirects_for_a_seeded_exercise(client, user, seeded_exercise):
    client.force_login(user)

    response = client.get(reverse("exercise_edit", kwargs={"pk": seeded_exercise.pk}))

    assert response.status_code == 302
    assert response.url == reverse("exercise_detail", kwargs={"pk": seeded_exercise.pk})
    seeded_exercise.refresh_from_db()
    assert seeded_exercise.name == "Barbell Bench Press"


@pytest.mark.django_db
def test_edit_returns_404_for_another_users_exercise(client, user, other_user, muscles):
    theirs = make_custom(other_user, muscles["Chest"])
    client.force_login(user)

    response = client.get(reverse("exercise_edit", kwargs={"pk": theirs.pk}))

    assert response.status_code == 404


# --- Archive and restore ----------------------------------------------------


@pytest.mark.django_db
def test_archive_a_seeded_exercise_creates_a_private_archive(client, user, seeded_exercise):
    client.force_login(user)

    response = client.post(reverse("exercise_archive", kwargs={"pk": seeded_exercise.pk}))

    assert response.status_code == 302
    assert ExerciseArchive.objects.filter(user=user, exercise=seeded_exercise).exists()
    seeded_exercise.refresh_from_db()
    assert seeded_exercise.user is None
    assert seeded_exercise.is_archived is False


@pytest.mark.django_db
def test_archive_a_custom_exercise_hides_it_from_the_library(client, user, custom_exercise):
    client.force_login(user)

    client.post(reverse("exercise_archive", kwargs={"pk": custom_exercise.pk}))

    custom_exercise.refresh_from_db()
    assert custom_exercise.is_archived is True
    library = client.get(reverse("library"))
    assert reverse("exercise_detail", kwargs={"pk": custom_exercise.pk}).encode() not in (
        library.content
    )


@pytest.mark.django_db
def test_restore_brings_a_seeded_exercise_back(client, user, seeded_exercise):
    ExerciseArchive.objects.create(user=user, exercise=seeded_exercise)
    client.force_login(user)

    client.post(reverse("exercise_restore", kwargs={"pk": seeded_exercise.pk}))

    assert not ExerciseArchive.objects.filter(user=user, exercise=seeded_exercise).exists()


@pytest.mark.django_db
def test_restore_brings_a_custom_exercise_back(client, user, custom_exercise):
    custom_exercise.is_archived = True
    custom_exercise.save(update_fields=["is_archived"])
    client.force_login(user)

    client.post(reverse("exercise_restore", kwargs={"pk": custom_exercise.pk}))

    custom_exercise.refresh_from_db()
    assert custom_exercise.is_archived is False


@pytest.mark.django_db
def test_archive_rejects_another_users_exercise(client, user, other_user, muscles):
    theirs = make_custom(other_user, muscles["Chest"])
    client.force_login(user)

    response = client.post(reverse("exercise_archive", kwargs={"pk": theirs.pk}))

    assert response.status_code == 404
    theirs.refresh_from_db()
    assert theirs.is_archived is False


@pytest.mark.django_db
def test_archive_requires_post(client, user, custom_exercise):
    client.force_login(user)

    response = client.get(reverse("exercise_archive", kwargs={"pk": custom_exercise.pk}))

    assert response.status_code == 405
