"""Account views."""

from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import PreferencesForm
from .services.settings import get_settings, update_preferences


def settings_view(request):
    """Theme and default rest (F-11, partial until M4)."""
    user_settings = get_settings(request.user)

    if request.method == "POST":
        form = PreferencesForm(request.POST, instance=user_settings)
        if form.is_valid():
            update_preferences(
                request.user,
                theme=form.cleaned_data["theme"],
                default_rest_seconds=form.cleaned_data["default_rest_seconds"],
            )
            messages.success(request, "Settings saved.")
            return redirect("settings")
    else:
        form = PreferencesForm(instance=user_settings)

    return render(
        request,
        "accounts/settings.html",
        {
            "page_title": "Settings",
            "form": form,
        },
    )
