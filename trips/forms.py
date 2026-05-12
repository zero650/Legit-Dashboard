from django import forms

from .models import Employee, Task, TaskTemplate, Trip


class DateInput(forms.DateInput):
    input_type = "date"


class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = [
            "name",
            "start_date",
            "end_date",
            "trip_manager",
            "status",
            "trip_leader",
            "notes",
        ]
        widgets = {
            "start_date": DateInput(),
            "end_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 8}),
        }
        labels = {
            "trip_leader": "Trip leader / host",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].queryset = self.fields["status"].queryset.filter(
            is_active=True,
        )
        self.fields["trip_manager"].queryset = Employee.objects.filter(
            roles__name__in=["Administrator", "Staff"],
        ).distinct()
        self.fields["trip_leader"].queryset = Employee.objects.filter(
            roles__name="Host",
        ).distinct()


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "name",
            "trip",
            "assigned_to",
            "status",
            "due_date",
            "days_to_before_trip",
            "notes",
        ]
        widgets = {
            "due_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }


class TaskCreateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "source_template",
            "trip",
            "assigned_to",
            "status",
            "due_date",
            "days_to_before_trip",
            "notes",
        ]
        widgets = {
            "due_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }
        labels = {
            "source_template": "Task template",
        }
        help_texts = {
            "due_date": "Optional. Leave blank to calculate from the template's day offset.",
            "days_to_before_trip": "Optional. Overrides the template's day offset. Negative is before the trip; positive is after.",
            "notes": "Optional. Leave blank to use the template's default notes.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_template"].queryset = TaskTemplate.objects.filter(is_active=True)
        self.fields["source_template"].required = True

    def save(self, commit=True):
        task = super().save(commit=False)
        template = self.cleaned_data["source_template"]
        task.name = template.name

        if task.days_to_before_trip is None and task.due_date is None:
            task.days_to_before_trip = template.days_to_before_trip

        if not task.notes:
            task.notes = template.default_notes

        if commit:
            task.save()
            self.save_m2m()
        return task


class TaskTemplateForm(forms.ModelForm):
    class Meta:
        model = TaskTemplate
        fields = [
            "name",
            "description",
            "default_notes",
            "days_to_before_trip",
            "sort_order",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "default_notes": forms.Textarea(attrs={"rows": 5}),
        }
