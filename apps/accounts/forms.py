"""Forms for account settings."""

from django import forms

from .models import UserSettings


class PreferencesForm(forms.ModelForm):
    """Theme and default rest for the signed-in user."""

    class Meta:
        model = UserSettings
        fields = ["theme", "default_rest_seconds"]
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
        }
        labels = {"default_rest_seconds": "Default rest (sec)"}
        help_texts = {
            "default_rest_seconds": "Used for new plan items. You can override it per item."
        }

    def clean_default_rest_seconds(self):
        seconds = self.cleaned_data["default_rest_seconds"]
        if seconds > 3600:
            raise forms.ValidationError("Keep rest at 60 minutes or less.")
        return seconds
