"""Forms for plans, plan days, and plan items (F-03)."""

from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.services.settings import get_settings
from apps.exercises.models import DistanceUnit, Exercise
from apps.exercises.services import units as distance_units

from .models import Plan, PlanDay, PlanItem
from .services.plans import clean_item_targets


class ExerciseSelect(forms.Select):
    """Add tracking type and default distance unit so the UI can adapt fields."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-tracking"] = instance.tracking_type
            option["attrs"]["data-unit"] = instance.default_distance_unit
        return option


class PlanForm(forms.ModelForm):
    """Name, split, start date, and optional fixed length."""

    class Meta:
        model = Plan
        fields = ["name", "split_type", "start_date", "length_weeks"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "ll-input",
                    "autocomplete": "off",
                    "placeholder": "e.g. Upper/Lower Block 3",
                }
            ),
            "split_type": forms.Select(attrs={"class": "ll-input"}),
            "start_date": forms.DateInput(attrs={"class": "ll-input", "type": "date"}),
            "length_weeks": forms.NumberInput(
                attrs={
                    "class": "ll-input",
                    "min": 1,
                    "max": 520,
                    "inputmode": "numeric",
                    "placeholder": "Leave blank to repeat",
                }
            ),
        }
        labels = {
            "length_weeks": "Length (weeks)",
        }
        help_texts = {
            "length_weeks": "Leave blank for an open-ended plan.",
        }
        error_messages = {
            "name": {"required": "Enter a plan name."},
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Enter a plan name.")
        return name

    def clean_length_weeks(self):
        length = self.cleaned_data["length_weeks"]
        if length is not None and length < 1:
            raise forms.ValidationError("Use at least one week.")
        return length


class PlanDayForm(forms.ModelForm):
    """A Plan Day name, weekday, and focus muscle groups."""

    class Meta:
        model = PlanDay
        fields = ["name", "weekday", "focus_muscles"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "ll-input",
                    "autocomplete": "off",
                    "placeholder": "e.g. Day A – Lower",
                }
            ),
            "weekday": forms.Select(attrs={"class": "ll-input"}),
            "focus_muscles": forms.CheckboxSelectMultiple,
        }
        labels = {
            "name": "Day name",
            "focus_muscles": "Focus muscles",
        }
        help_texts = {
            "focus_muscles": "These groups appear first in the exercise picker.",
        }

    def __init__(self, *args, plan, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan = plan
        self.fields["focus_muscles"].required = False
        self.fields["focus_muscles"].queryset = self.fields["focus_muscles"].queryset.order_by(
            "display_order", "name"
        )

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Enter a day name.")
        return name

    def clean_weekday(self):
        weekday = self.cleaned_data["weekday"]
        clash = self.plan.days.filter(weekday=weekday)
        if self.instance.pk is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("That weekday already has a day in this plan.")
        return weekday


class PlanItemForm(forms.ModelForm):
    """Exercise, targets by tracking type, rest, and notes."""

    target_distance = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=4,
        label="Target distance",
        widget=forms.NumberInput(
            attrs={
                "class": "ll-input",
                "min": 0,
                "step": "any",
                "inputmode": "decimal",
            }
        ),
    )
    distance_unit = forms.ChoiceField(
        required=False,
        label="Distance unit",
        choices=(("", "Exercise default"), *DistanceUnit.choices),
        widget=forms.Select(attrs={"class": "ll-input", "x-model": "unit"}),
    )

    class Meta:
        model = PlanItem
        fields = [
            "exercise",
            "target_sets",
            "rep_min",
            "rep_max",
            "target_seconds",
            "rest_seconds",
            "notes",
        ]
        widgets = {
            "exercise": ExerciseSelect(attrs={"class": "ll-input"}),
            "target_sets": forms.NumberInput(
                attrs={"class": "ll-input", "min": 1, "max": 99, "inputmode": "numeric"}
            ),
            "rep_min": forms.NumberInput(
                attrs={"class": "ll-input", "min": 1, "max": 999, "inputmode": "numeric"}
            ),
            "rep_max": forms.NumberInput(
                attrs={"class": "ll-input", "min": 1, "max": 999, "inputmode": "numeric"}
            ),
            "target_seconds": forms.NumberInput(
                attrs={
                    "class": "ll-input",
                    "min": 1,
                    "max": 86400,
                    "inputmode": "numeric",
                }
            ),
            "rest_seconds": forms.NumberInput(
                attrs={
                    "class": "ll-input",
                    "min": 0,
                    "max": 3600,
                    "step": 5,
                    "inputmode": "numeric",
                }
            ),
            "notes": forms.TextInput(
                attrs={
                    "class": "ll-input",
                    "autocomplete": "off",
                    "placeholder": "Optional cues or setup",
                }
            ),
        }
        labels = {
            "exercise": "Exercise",
            "target_sets": "Sets",
            "rep_min": "Rep min",
            "rep_max": "Rep max",
            "target_seconds": "Target seconds",
            "rest_seconds": "Rest (sec)",
            "notes": "Notes / cues",
        }

    def __init__(self, *args, user, day, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.day = day
        self.fields["exercise"].queryset = Exercise.objects.visible_to(user).select_related(
            "primary_muscle"
        )
        self.fields["exercise"].widget.attrs.update(
            {
                "x-on:change": (
                    "tracking = $event.target.selectedOptions[0]?.dataset.tracking || ''; "
                    "unit = $event.target.selectedOptions[0]?.dataset.unit || ''"
                )
            }
        )
        self.fields["notes"].required = False
        if self.instance.pk is None:
            self.initial.setdefault("target_sets", 3)
            self.initial.setdefault("rest_seconds", get_settings(user).default_rest_seconds)
        elif not self.is_bound:
            self.initial.setdefault(
                "target_distance",
                distance_units.display_value(
                    self.instance.target_distance_m,
                    self.instance.distance_unit,
                ),
            )
            self.initial.setdefault("distance_unit", self.instance.distance_unit)

    def clean(self):
        cleaned_data = super().clean()
        exercise = cleaned_data.get("exercise")
        if exercise is None:
            return cleaned_data
        unit = distance_units.normalize_unit(
            cleaned_data.get("distance_unit") or exercise.default_distance_unit
        )
        display_distance = cleaned_data.get("target_distance")
        target_distance_m = distance_units.to_meters(display_distance, unit)
        try:
            targets = clean_item_targets(
                exercise,
                target_sets=cleaned_data.get("target_sets"),
                rep_min=cleaned_data.get("rep_min"),
                rep_max=cleaned_data.get("rep_max"),
                target_seconds=cleaned_data.get("target_seconds"),
                target_distance_m=target_distance_m,
                distance_unit=unit,
                rest_seconds=cleaned_data.get("rest_seconds"),
            )
        except ValidationError as error:
            for field, messages in error.message_dict.items():
                self.add_error(
                    "target_distance" if field == "target_distance_m" else field,
                    messages,
                )
        else:
            cleaned_data.update(targets)
        cleaned_data.pop("target_distance", None)
        return cleaned_data

    @property
    def selected_tracking(self) -> str:
        if self.is_bound:
            exercise_id = self.data.get("exercise")
            if exercise_id:
                exercise = (
                    Exercise.objects.visible_to(self.user)
                    .filter(pk=exercise_id)
                    .only("tracking_type")
                    .first()
                )
                if exercise is not None:
                    return exercise.tracking_type
        elif self.instance.pk is not None:
            return self.instance.exercise.tracking_type
        elif self.initial.get("exercise"):
            exercise = (
                Exercise.objects.visible_to(self.user)
                .filter(pk=self.initial["exercise"])
                .only("tracking_type")
                .first()
            )
            if exercise is not None:
                return exercise.tracking_type
        return ""
