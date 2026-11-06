"""Navigation metadata shared by the phone tab bar and tablet sidebar."""

from django.urls import NoReverseMatch, reverse

NAV_ITEMS = [
    {
        "url_name": "today",
        "label": "Today",
        "icon": "calendar-check",
        "active_url_names": {"today"},
    },
    {
        "url_name": "plans",
        "label": "Plan",
        "icon": "clipboard-list",
        "active_url_names": {
            "plans",
            "plan_new",
            "plan_detail",
            "plan_item_new",
            "plan_item_edit",
        },
    },
    {
        "url_name": "library",
        "label": "Library",
        "icon": "library",
        "active_url_names": {
            "library",
            "exercise_detail",
            "exercise_new",
            "exercise_edit",
        },
    },
    {
        "url_name": "history",
        "label": "History",
        "icon": "history",
        "active_url_names": {"history"},
    },
    {
        "url_name": "stats",
        "label": "Stats",
        "icon": "chart-line",
        "active_url_names": {"stats"},
    },
]


def navigation(request):
    """Expose nav items with resolved URLs and the active state."""
    match = getattr(request, "resolver_match", None)
    current = match.url_name if match else None
    items = []
    for item in NAV_ITEMS:
        try:
            url = reverse(item["url_name"])
        except NoReverseMatch:
            continue
        items.append(
            {
                "url": url,
                "label": item["label"],
                "icon": item["icon"],
                "is_active": current in item["active_url_names"],
            }
        )
    return {"nav_items": items}
