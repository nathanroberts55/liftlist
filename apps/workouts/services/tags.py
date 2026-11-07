"""Tag services (F-06).

Tags are always scoped to one user. Names are unique per user, ignoring case.
Colors come from the DESIGN chart palette so the UI follows the theme's fixed
color language instead of accepting arbitrary values.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count

from ..models import Tag

# DESIGN §2 chart palette, in order.
TAG_PALETTE = (
    ("#2B7FFF", "Blue"),
    ("#64D2FF", "Cyan"),
    ("#FF9F0A", "Amber"),
    ("#30D158", "Green"),
    ("#BF5AF2", "Purple"),
    ("#FF375F", "Pink"),
    ("#AC8E68", "Brown"),
    ("#8E8E93", "Gray"),
)
TAG_COLORS = {value for value, _label in TAG_PALETTE}
DEFAULT_TAG_COLOR = TAG_PALETTE[0][0]


def list_tags(user):
    """A user's tags with the number of sessions that use each one."""
    return Tag.objects.filter(user=user).annotate(session_count=Count("sessions")).order_by("name")


def get_tag(user, tag_id) -> Tag:
    from django.shortcuts import get_object_or_404

    return get_object_or_404(Tag.objects.filter(user=user), pk=tag_id)


def _clean_name(name) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValidationError("Enter a tag name.")
    if len(cleaned) > 30:
        raise ValidationError("Keep tag names to 30 characters or fewer.")
    return cleaned


def _clean_color(color) -> str:
    if color not in TAG_COLORS:
        raise ValidationError("Pick a color from the palette.")
    return color


def _assert_unique_name(user, name, *, exclude_pk=None) -> None:
    clash = Tag.objects.filter(user=user, name__iexact=name)
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        raise ValidationError("You already have a tag with that name.")


@transaction.atomic
def create_tag(user, *, name, color) -> Tag:
    name = _clean_name(name)
    color = _clean_color(color)
    _assert_unique_name(user, name)
    return Tag.objects.create(user=user, name=name, color=color)


@transaction.atomic
def update_tag(user, tag: Tag, *, name, color) -> Tag:
    if tag.user_id != user.pk:
        raise ValidationError("That tag does not belong to you.")
    name = _clean_name(name)
    color = _clean_color(color)
    _assert_unique_name(user, name, exclude_pk=tag.pk)
    tag.name = name
    tag.color = color
    tag.save(update_fields=["name", "color", "updated_at"])
    return tag


@transaction.atomic
def delete_tag(user, tag: Tag) -> None:
    if tag.user_id != user.pk:
        raise ValidationError("That tag does not belong to you.")
    tag.delete()


def resolve_tags(user, tag_ids) -> list[Tag]:
    """Return the user's tags for ``tag_ids``, rejecting foreign ids."""
    ids = []
    for raw in tag_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError) as error:
            raise ValidationError("Pick a valid tag.") from error
    tags = list(Tag.objects.filter(user=user, pk__in=ids))
    if len(tags) != len(set(ids)):
        raise ValidationError("Pick a valid tag.")
    return tags


def default_tags(user) -> list[Tag]:
    """The tags pre-selected on new unscheduled sessions."""
    return list(Tag.objects.filter(user=user, default_for_settings__user=user).order_by("name"))


def set_default_tags(user, tag_ids) -> None:
    from apps.accounts.services.settings import get_settings

    get_settings(user).default_tags.set(resolve_tags(user, tag_ids))
