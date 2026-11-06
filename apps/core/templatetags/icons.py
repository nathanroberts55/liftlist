"""Inline Lucide icons for templates."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ._icon_data import ICONS

register = template.Library()


@register.simple_tag
def icon(name, css_class="size-6", stroke_width=2):
    """Render a Lucide icon. Unknown names render nothing."""
    inner = ICONS.get(name)
    if inner is None:
        return ""
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="{}" stroke-linecap="round" '
        'stroke-linejoin="round" class="{}" aria-hidden="true" focusable="false">{}</svg>',
        stroke_width,
        css_class,
        mark_safe(inner),  # noqa: S308 - trusted build-time icon data
    )
