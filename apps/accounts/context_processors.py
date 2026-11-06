"""Template context for the active theme (DESIGN §2 and §8)."""

from .models import UserSettings

DARK_THEME = "liftlist-dark"
LIGHT_THEME = "liftlist-light"

THEME_COLORS = {
    DARK_THEME: "#0B0D10",
    LIGHT_THEME: "#F5F6F8",
}


def theme(request):
    """Resolve the user's theme preference into a DaisyUI theme name.

    ``SYSTEM`` falls back to dark on the server; a tiny inline script in
    base.html switches to light before first paint when the device prefers it.
    """
    preference = UserSettings.Theme.DARK
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        user_settings = getattr(user, "settings", None)
        if user_settings is not None:
            preference = user_settings.theme

    resolved = LIGHT_THEME if preference == UserSettings.Theme.LIGHT else DARK_THEME

    return {
        "theme": resolved,
        "theme_preference": preference,
        "theme_color": THEME_COLORS[resolved],
        "theme_color_dark": THEME_COLORS[DARK_THEME],
        "theme_color_light": THEME_COLORS[LIGHT_THEME],
    }
