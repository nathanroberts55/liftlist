"""Forms for account settings."""

from django import forms
from django.contrib.auth.forms import PasswordChangeForm

from apps.workouts.models import Tag

from .models import UserSettings


class PreferencesForm(forms.ModelForm):
    """Theme, default rest, timer sound, and default tags for the signed-in user."""

    default_tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = UserSettings
        fields = ["theme", "default_rest_seconds", "timer_sound"]
        widgets = {
            "theme": forms.RadioSelect(
                attrs={
                    "class": "theme-option-input",
                    "aria-label": "Theme",
                }
            ),
            "default_rest_seconds": forms.NumberInput(
                attrs={
                    "class": "ll-input",
                    "min": 0,
                    "max": 3600,
                    "step": 5,
                    "inputmode": "numeric",
                }
            ),
            "timer_sound": forms.CheckboxInput(
                attrs={
                    "class": "toggle toggle-primary",
                    "role": "switch",
                }
            ),
        }
        labels = {
            "default_rest_seconds": "Default rest (sec)",
            "timer_sound": "Timer sound",
        }
        help_texts = {
            "default_rest_seconds": "Used for new plan items. You can override it per item.",
            "timer_sound": "Play a short beep when a rest timer finishes.",
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["default_tags"].queryset = Tag.objects.filter(user=user).order_by("name")

    def clean_default_rest_seconds(self):
        seconds = self.cleaned_data["default_rest_seconds"]
        if seconds > 3600:
            raise forms.ValidationError("Keep rest at 60 minutes or less.")
        return seconds

    @property
    def selected_tag_ids(self) -> set[int]:
        if self.is_bound:
            return {
                int(value)
                for value in self.data.getlist(self.add_prefix("default_tags"))
                if str(value).isdigit()
            }
        if self.instance is not None and self.instance.pk:
            return set(self.instance.default_tags.values_list("pk", flat=True))
        return {tag.pk for tag in self.initial.get("default_tags", [])}


class StyledPasswordChangeForm(PasswordChangeForm):
    """Django's password form with the app's input styling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "ll-input")
