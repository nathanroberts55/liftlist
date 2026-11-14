"""Forms for creating and editing custom exercises."""

from django import forms

from .models import DistanceUnit, Exercise, MuscleGroup
from .services.library import validate_name


class ExerciseForm(forms.Form):
    """Name, muscles, tracking type, and notes for a custom exercise."""

    name = forms.CharField(
        max_length=100,
        strip=True,
        label="Name",
        error_messages={"required": "Enter an exercise name."},
        widget=forms.TextInput(
            attrs={
                "class": "ll-input",
                "autocomplete": "off",
                "placeholder": "e.g. Barbell Bench Press",
            }
        ),
    )
    primary_muscle = forms.ModelChoiceField(
        queryset=MuscleGroup.objects.all(),
        label="Primary muscle",
        empty_label="Choose a muscle group",
        widget=forms.Select(attrs={"class": "ll-input"}),
    )
    tracking_type = forms.ChoiceField(
        choices=Exercise.TrackingType.choices,
        label="Tracking type",
        widget=forms.Select(attrs={"class": "ll-input", "x-model": "tracking"}),
    )
    default_distance_unit = forms.ChoiceField(
        choices=DistanceUnit.choices,
        label="Default distance unit",
        required=False,
        widget=forms.Select(attrs={"class": "ll-input"}),
    )
    secondary_muscles = forms.ModelMultipleChoiceField(
        queryset=MuscleGroup.objects.all(),
        required=False,
        label="Secondary muscles",
        widget=forms.CheckboxSelectMultiple,
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.Textarea(
            attrs={
                "class": "ll-input h-auto min-h-24 py-3",
                "rows": 3,
                "placeholder": "Optional cues, setup, or machine settings",
            }
        ),
    )

    field_order = [
        "name",
        "primary_muscle",
        "tracking_type",
        "default_distance_unit",
        "secondary_muscles",
        "notes",
    ]

    def __init__(self, *args, user, exclude: Exercise | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.exclude = exclude

    def clean_name(self):
        return validate_name(
            self.user,
            self.cleaned_data["name"],
            exclude=self.exclude,
        )

    def clean_default_distance_unit(self):
        return self.cleaned_data.get("default_distance_unit") or DistanceUnit.MILES

    def clean(self):
        cleaned_data = super().clean()
        primary = cleaned_data.get("primary_muscle")
        secondary = cleaned_data.get("secondary_muscles")
        if primary and secondary and primary in secondary:
            self.add_error(
                "secondary_muscles",
                "The primary muscle can't also be a secondary muscle.",
            )
        return cleaned_data
