"""Account views."""

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from apps.workouts.services import tags as tag_services

from .forms import PreferencesForm, StyledPasswordChangeForm
from .services.settings import get_settings, update_preferences


def settings_view(request):
    """Theme, rest, sound, default tags, and tag management (F-11)."""
    user_settings = get_settings(request.user)

    if request.method == "POST":
        form = PreferencesForm(request.POST, instance=user_settings, user=request.user)
        if form.is_valid():
            update_preferences(
                request.user,
                theme=form.cleaned_data["theme"],
                default_rest_seconds=form.cleaned_data["default_rest_seconds"],
                timer_sound=form.cleaned_data["timer_sound"],
                default_tag_ids=[tag.pk for tag in form.cleaned_data["default_tags"]],
            )
            messages.success(request, "Settings saved.")
            return redirect("settings")
    else:
        form = PreferencesForm(instance=user_settings, user=request.user)

    return render(
        request,
        "accounts/settings.html",
        {
            "page_title": "Settings",
            "form": form,
            "tags": tag_services.list_tags(request.user),
        },
    )


class PasswordChangeView(auth_views.PasswordChangeView):
    """Change password, then return to Settings with a confirmation message."""

    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("settings")

    def form_valid(self, form):
        messages.success(self.request, "Password changed.")
        return super().form_valid(form)
