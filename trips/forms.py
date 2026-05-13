from django import forms

from .models import Employee, Task, TaskTemplate, TaskTemplatePack, Trip


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
            "name",
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
            "name": "Task name",
            "source_template": "Task template",
        }
        help_texts = {
            "name": "Optional for one-off tasks. Leave blank to use the selected template name.",
            "due_date": "Optional. Leave blank to calculate from the template's day offset.",
            "days_to_before_trip": "Optional. Overrides the template's day offset. Negative is before the trip; positive is after.",
            "notes": "Optional. Leave blank to use the template's default notes.",
            "source_template": "Optional. Choose a template for standard trip tasks.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_template"].queryset = TaskTemplate.objects.filter(is_active=True)
        self.fields["source_template"].required = False
        self.fields["name"].required = False

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("source_template") and not cleaned_data.get("name"):
            error = "Choose a task template or enter a name for a one-off task."
            self.add_error("source_template", error)
            self.add_error("name", error)
        return cleaned_data

    def save(self, commit=True):
        task = super().save(commit=False)
        template = self.cleaned_data.get("source_template")
        if template:
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


class TaskTemplatePackForm(forms.ModelForm):
    class Meta:
        model = TaskTemplatePack
        fields = [
            "name",
            "description",
            "task_templates",
            "sort_order",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "task_templates": forms.CheckboxSelectMultiple(),
        }
        help_texts = {
            "task_templates": "Select the task templates that belong in this pack.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["task_templates"].queryset = TaskTemplate.objects.filter(is_active=True)


class TaskQuickUpdateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["assigned_to", "status", "due_date"]
        widgets = {
            "due_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = Employee.objects.select_related("user")
        self.fields["assigned_to"].required = False
        self.fields["due_date"].required = False

    def save(self, commit=True):
        task = super().save(commit=False)
        if "due_date" in self.changed_data:
            task.days_to_before_trip = None
        if commit:
            task.save()
            self.save_m2m()
        return task


class TripQuickUpdateForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = ["trip_leader", "trip_manager", "status", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["trip_manager"].queryset = Employee.objects.filter(
            roles__name__in=["Administrator", "Staff"],
        ).distinct()
        self.fields["trip_leader"].queryset = Employee.objects.filter(
            roles__name="Host",
        ).distinct()
        self.fields["status"].queryset = self.fields["status"].queryset.filter(
            is_active=True,
        )
        self.fields["trip_leader"].required = False
        self.fields["notes"].required = False
