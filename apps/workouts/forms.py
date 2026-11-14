"""Forms for tags, unscheduled sessions, history editing, and set entry."""

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.services.settings import get_settings
from apps.exercises.models import DistanceUnit, Exercise
from apps.exercises.services import units as distance_units
from apps.plans.forms import ExerciseSelect
from apps.plans.services.plans import clean_item_targets

from .models import Tag
from .services import runner
from .services import tags as tag_services

ITEM_TARGET_FIELDS = (
    "target_sets",
    "rep_min",
    "rep_max",
    "target_seconds",
    "rest_seconds",
)


class TagForm(forms.Form):
    """Create or rename a tag and pick one palette color."""

    name = forms.CharField(
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "class": "ll-input",
                "autocomplete": "off",
                "placeholder": "e.g. PT",
            }
        ),
        error_messages={"required": "Enter a tag name."},
    )
    color = forms.ChoiceField(
        choices=tag_services.TAG_PALETTE,
        widget=forms.RadioSelect(attrs={"class": "tag-color-input"}),
    )

    def __init__(self, *args, user, tag=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.tag = tag

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Enter a tag name.")
        return name

    def clean(self):
        cleaned = super().clean()
        name = cleaned.get("name")
        if name:
            clash = Tag.objects.filter(user=self.user, name__iexact=name)
            if self.tag is not None:
                clash = clash.exclude(pk=self.tag.pk)
            if clash.exists():
                self.add_error("name", "You already have a tag with that name.")
        return cleaned


class SessionTagsMixin(forms.Form):
    """Shared tag field scoped to the signed-in user."""

    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def _setup_tags(self, user, *, use_defaults=False):
        self.fields["tags"].queryset = Tag.objects.filter(user=user).order_by("name")
        if use_defaults and not self.is_bound:
            self.initial.setdefault("tags", tag_services.default_tags(user))

    @property
    def selected_tag_ids(self) -> set[int]:
        if self.is_bound:
            return {
                int(value)
                for value in self.data.getlist(self.add_prefix("tags"))
                if str(value).isdigit()
            }
        initial = self.initial.get("tags") or []
        return {tag.pk for tag in initial}


class SessionItemForm(forms.Form):
    """One exercise row with targets for a new unscheduled session."""

    # Blank extra rows must not be browser-required; the formset validates that
    # at least one row has an exercise on the server.
    use_required_attribute = False

    exercise = forms.ModelChoiceField(
        queryset=Exercise.objects.none(),
        empty_label="Choose exercise",
        widget=ExerciseSelect(
            attrs={
                "class": "ll-input",
                "x-on:change": (
                    "tracking = $event.target.selectedOptions[0]?.dataset.tracking || ''; "
                    "unit = $event.target.selectedOptions[0]?.dataset.unit || ''"
                ),
            }
        ),
    )
    target_sets = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=99,
        widget=forms.NumberInput(
            attrs={"class": "ll-input", "min": 1, "max": 99, "inputmode": "numeric"}
        ),
    )
    rep_min = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=999,
        widget=forms.NumberInput(
            attrs={"class": "ll-input", "min": 1, "max": 999, "inputmode": "numeric"}
        ),
    )
    rep_max = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=999,
        widget=forms.NumberInput(
            attrs={"class": "ll-input", "min": 1, "max": 999, "inputmode": "numeric"}
        ),
    )
    target_seconds = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=86400,
        widget=forms.NumberInput(
            attrs={"class": "ll-input", "min": 1, "max": 86400, "inputmode": "numeric"}
        ),
    )
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
    rest_seconds = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=3600,
        widget=forms.NumberInput(
            attrs={
                "class": "ll-input",
                "min": 0,
                "max": 3600,
                "step": 5,
                "inputmode": "numeric",
            }
        ),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["exercise"].queryset = Exercise.objects.visible_to(user).select_related(
            "primary_muscle"
        )
        if not self.is_bound:
            self.initial.setdefault("target_sets", 3)
            self.initial.setdefault("rest_seconds", get_settings(user).default_rest_seconds)

    def clean(self):
        cleaned = super().clean()
        exercise = cleaned.get("exercise")
        if exercise is None:
            return cleaned
        targets = {field: cleaned.get(field) for field in ITEM_TARGET_FIELDS}
        if targets["target_sets"] in (None, ""):
            targets["target_sets"] = 3
        if targets["rest_seconds"] in (None, ""):
            targets["rest_seconds"] = get_settings(self.user).default_rest_seconds
        unit = distance_units.normalize_unit(
            cleaned.get("distance_unit") or exercise.default_distance_unit
        )
        targets["target_distance_m"] = distance_units.to_meters(
            cleaned.get("target_distance"),
            unit,
        )
        targets["distance_unit"] = unit
        try:
            cleaned.update(clean_item_targets(exercise, **targets))
        except ValidationError as error:
            for field, messages in error.message_dict.items():
                self.add_error(
                    "target_distance" if field == "target_distance_m" else field,
                    messages,
                )
        cleaned.pop("target_distance", None)
        return cleaned

    @property
    def selected_tracking(self) -> str:
        if self.is_bound:
            exercise_id = self.data.get(self.add_prefix("exercise"))
            if exercise_id:
                exercise = (
                    Exercise.objects.visible_to(self.user)
                    .filter(pk=exercise_id)
                    .only("tracking_type")
                    .first()
                )
                if exercise is not None:
                    return exercise.tracking_type
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


class BaseSessionItemFormSet(forms.BaseFormSet):
    """Require at least one exercise row with a selected exercise."""

    def clean(self):
        super().clean()
        if any(form.has_changed() and form.errors for form in self.forms):
            return
        chosen = [
            form
            for form in self.forms
            if getattr(form, "cleaned_data", None) and form.cleaned_data.get("exercise")
        ]
        if not chosen:
            raise ValidationError("Add at least one exercise.")


SessionItemFormSet = forms.formset_factory(
    SessionItemForm,
    formset=BaseSessionItemFormSet,
    extra=1,
)


class UnscheduledSessionForm(SessionTagsMixin):
    """Title, tags, and exercise rows for a plan-and-start session."""

    title = forms.CharField(
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "ll-input",
                "autocomplete": "off",
                "placeholder": "e.g. Push day",
            }
        ),
        error_messages={"required": "Enter a workout title."},
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._setup_tags(user, use_defaults=True)

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Enter a workout title.")
        return title


class RetroSessionForm(SessionTagsMixin):
    """Title, date, optional time/duration, tags, and exercise rows."""

    title = forms.CharField(
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "ll-input",
                "autocomplete": "off",
                "placeholder": "e.g. PT session",
            }
        ),
    )
    performed_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "ll-input", "type": "date"}),
    )
    start_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"class": "ll-input", "type": "time"}),
    )
    duration_minutes = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=1440,
        widget=forms.NumberInput(
            attrs={"class": "ll-input", "min": 0, "max": 1440, "inputmode": "numeric"}
        ),
        label="Duration (minutes)",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._setup_tags(user, use_defaults=True)

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Enter a workout title.")
        return title

    def clean_performed_date(self):
        performed = self.cleaned_data["performed_date"]
        if performed > timezone.localdate():
            raise forms.ValidationError("Pick today or a past date.")
        return performed

    @property
    def duration_seconds(self) -> int | None:
        minutes = self.cleaned_data.get("duration_minutes")
        return minutes * 60 if minutes else None


class SessionEditForm(SessionTagsMixin):
    """Change a session's title, performed date, and tags."""

    title = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"class": "ll-input"}))
    performed_date = forms.DateField(
        widget=forms.DateInput(attrs={"class": "ll-input", "type": "date"}),
    )

    def __init__(self, *args, user, session, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.session = session
        self._setup_tags(user)
        if not self.is_bound:
            self.initial.setdefault("title", session.title)
            self.initial.setdefault("performed_date", session.performed_date)
            self.initial.setdefault("tags", list(session.tags.all()))

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Enter a workout title.")
        return title

    def clean_performed_date(self):
        performed = self.cleaned_data["performed_date"]
        if performed > timezone.localdate():
            raise forms.ValidationError("Pick today or a past date.")
        return performed


class SetLogForm(forms.Form):
    """Weight/reps/duration/distance/difficulty for one set."""

    weight_lb = forms.DecimalField(
        required=False,
        max_digits=6,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "ll-input",
                "min": 0,
                "step": "5",
                "inputmode": "decimal",
            }
        ),
        label="Weight (lb)",
    )
    reps = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=1000,
        widget=forms.NumberInput(attrs={"class": "ll-input", "min": 1, "inputmode": "numeric"}),
    )
    duration = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "ll-input",
                "placeholder": "mm:ss",
                "inputmode": "numeric",
            }
        ),
        label="Duration",
    )
    distance = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=4,
        widget=forms.NumberInput(
            attrs={"class": "ll-input", "min": 0, "step": "any", "inputmode": "decimal"}
        ),
        label="Distance",
    )
    difficulty = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        widget=forms.NumberInput(
            attrs={"class": "ll-input", "min": 1, "max": 10, "inputmode": "numeric"}
        ),
    )

    def __init__(self, *args, tracking_type, distance_unit=DistanceUnit.MILES, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracking_type = tracking_type
        self.distance_unit = distance_units.normalize_unit(distance_unit)
        self.fields["distance"].label = f"Distance ({self.distance_unit.short_label})"
        if tracking_type == Exercise.TrackingType.DISTANCE:
            self.fields["reps"].label = "Steps (each way)"

    def clean(self):
        cleaned = super().clean()
        try:
            values = runner.validate_set_fields(
                self.tracking_type,
                cleaned,
                distance_unit=self.distance_unit,
            )
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error
        cleaned.update(values)
        return cleaned
