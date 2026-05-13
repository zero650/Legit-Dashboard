import csv
import io

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.dateparse import parse_date

from .models import WorkTask, WorkTaskTemplate, WorkTaskTemplatePack
from trips.models import Employee, Task, TaskTemplate, Trip


class TaskCsvImportForm(forms.Form):
    csv_file = forms.FileField(
        help_text=(
            "CSV columns: name, trip_id, assigned_to_email, status, due_date, "
            "days_to_before_trip, notes"
        )
    )


class TaskTemplateCsvImportForm(forms.Form):
    csv_file = forms.FileField(
        help_text=(
            "CSV columns: name, description, default_notes, days_to_before_trip, "
            "sort_order, is_active"
        )
    )


@admin.register(WorkTask)
class WorkTaskAdmin(admin.ModelAdmin):
    list_display = ("name", "trip", "source_template", "assigned_to", "status", "due_date")
    list_filter = ("status", "assigned_to", "trip__status", "source_template")
    search_fields = ("name", "notes", "assigned_to__user__email")
    autocomplete_fields = ("trip",)
    change_list_template = "admin/work_tasks/worktask/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="work_tasks_worktask_import_csv",
            ),
        ]
        return custom_urls + urls

    def import_csv_view(self, request):
        form = TaskCsvImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            csv_file = form.cleaned_data["csv_file"]
            decoded = csv_file.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(decoded))

            required_columns = {"name", "trip_id"}
            if not reader.fieldnames:
                self.message_user(request, "The uploaded CSV is empty.", level=messages.ERROR)
                return HttpResponseRedirect(request.path)

            missing_columns = required_columns - set(reader.fieldnames)
            if missing_columns:
                self.message_user(
                    request,
                    f"Missing required columns: {', '.join(sorted(missing_columns))}.",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect(request.path)

            try:
                tasks_to_create = self._build_tasks_from_csv(reader)
            except ValidationError as exc:
                for message in exc.messages:
                    self.message_user(request, message, level=messages.ERROR)
                return HttpResponseRedirect(request.path)

            with transaction.atomic():
                for task in tasks_to_create:
                    task.save()

            self.message_user(
                request,
                f"Imported {len(tasks_to_create)} tasks successfully.",
                level=messages.SUCCESS,
            )
            changelist_url = reverse("admin:work_tasks_worktask_changelist")
            return HttpResponseRedirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "form": form,
            "title": "Import Tasks from CSV",
        }
        return render(request, "admin/work_tasks/worktask/import_csv.html", context)

    def _build_tasks_from_csv(self, reader):
        tasks = []
        errors = []

        for index, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue

            trip_id = (row.get("trip_id") or "").strip()
            if not trip_id.isdigit():
                errors.append(f"Row {index}: trip_id must be a numeric trip ID.")
                continue

            trip = Trip.objects.filter(pk=int(trip_id)).first()
            if not trip:
                errors.append(f"Row {index}: trip_id {trip_id} was not found.")
                continue

            assigned_to = None
            assigned_to_email = (row.get("assigned_to_email") or "").strip()
            if assigned_to_email:
                assigned_to = Employee.objects.filter(
                    user__email__iexact=assigned_to_email
                ).first()
                if not assigned_to:
                    errors.append(
                        f"Row {index}: assigned_to_email {assigned_to_email} was not found."
                    )
                    continue

            status = self._parse_status(row.get("status"), index, errors)
            if status is None and (row.get("status") or "").strip():
                continue

            due_date = None
            due_date_raw = (row.get("due_date") or "").strip()
            if due_date_raw:
                due_date = parse_date(due_date_raw)
                if due_date is None:
                    errors.append(
                        f"Row {index}: due_date must be in YYYY-MM-DD format."
                    )
                    continue

            days_to_before_trip = None
            days_raw = (row.get("days_to_before_trip") or "").strip()
            if days_raw:
                try:
                    days_to_before_trip = int(days_raw)
                except ValueError:
                    errors.append(
                        f"Row {index}: days_to_before_trip must be an integer."
                    )
                    continue

            task = Task(
                name=(row.get("name") or "").strip(),
                trip=trip,
                assigned_to=assigned_to,
                status=status or Task.Status.NOT_STARTED,
                due_date=due_date,
                days_to_before_trip=days_to_before_trip,
                notes=(row.get("notes") or "").strip(),
            )
            try:
                task.full_clean()
            except ValidationError as exc:
                for field, field_errors in exc.message_dict.items():
                    for field_error in field_errors:
                        errors.append(f"Row {index}: {field} - {field_error}")
                continue

            tasks.append(task)

        if errors:
            raise ValidationError(errors)
        return tasks

    def _parse_status(self, raw_status, row_number, errors):
        status = (raw_status or "").strip()
        if not status:
            return None

        status_map = {
            Task.Status.NOT_STARTED: Task.Status.NOT_STARTED,
            Task.Status.IN_PROGRESS: Task.Status.IN_PROGRESS,
            Task.Status.DONE: Task.Status.DONE,
            "not started": Task.Status.NOT_STARTED,
            "in progress": Task.Status.IN_PROGRESS,
            "done": Task.Status.DONE,
        }
        normalized = status_map.get(status.lower())
        if not normalized:
            errors.append(
                f"Row {row_number}: status must be one of not_started, in_progress, done."
            )
        return normalized


@admin.register(WorkTaskTemplate)
class WorkTaskTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "days_to_before_trip", "sort_order", "is_active")
    list_editable = ("days_to_before_trip", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description", "default_notes")
    change_list_template = "admin/work_tasks/worktasktemplate/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="work_tasks_worktasktemplate_import_csv",
            ),
        ]
        return custom_urls + urls

    def import_csv_view(self, request):
        form = TaskTemplateCsvImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            csv_file = form.cleaned_data["csv_file"]
            decoded = csv_file.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(decoded))

            required_columns = {"name"}
            if not reader.fieldnames:
                self.message_user(request, "The uploaded CSV is empty.", level=messages.ERROR)
                return HttpResponseRedirect(request.path)

            missing_columns = required_columns - set(reader.fieldnames)
            if missing_columns:
                self.message_user(
                    request,
                    f"Missing required columns: {', '.join(sorted(missing_columns))}.",
                    level=messages.ERROR,
                )
                return HttpResponseRedirect(request.path)

            try:
                template_payloads = self._build_task_templates_from_csv(reader)
            except ValidationError as exc:
                for message in exc.messages:
                    self.message_user(request, message, level=messages.ERROR)
                return HttpResponseRedirect(request.path)

            with transaction.atomic():
                for payload in template_payloads:
                    TaskTemplate.objects.update_or_create(
                        name=payload["name"],
                        defaults=payload,
                    )

            self.message_user(
                request,
                f"Imported {len(template_payloads)} task templates successfully.",
                level=messages.SUCCESS,
            )
            changelist_url = reverse("admin:work_tasks_worktasktemplate_changelist")
            return HttpResponseRedirect(changelist_url)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "form": form,
            "title": "Import Task Templates from CSV",
            "column_help": [
                "name",
                "description",
                "default_notes",
                "days_to_before_trip",
                "sort_order",
                "is_active",
            ],
        }
        return render(request, "admin/work_tasks/worktasktemplate/import_csv.html", context)

    def _build_task_templates_from_csv(self, reader):
        payloads = []
        errors = []

        for index, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue

            name = (row.get("name") or "").strip()
            if not name:
                errors.append(f"Row {index}: name is required.")
                continue

            days_to_before_trip = None
            days_raw = (row.get("days_to_before_trip") or "").strip()
            if days_raw:
                try:
                    days_to_before_trip = int(days_raw)
                except ValueError:
                    errors.append(f"Row {index}: days_to_before_trip must be an integer.")
                    continue

            sort_order = 0
            sort_order_raw = (row.get("sort_order") or "").strip()
            if sort_order_raw:
                try:
                    sort_order = int(sort_order_raw)
                except ValueError:
                    errors.append(f"Row {index}: sort_order must be an integer.")
                    continue

            is_active = True
            is_active_raw = (row.get("is_active") or "").strip()
            if is_active_raw:
                parsed = self._parse_bool(is_active_raw)
                if parsed is None:
                    errors.append(f"Row {index}: is_active must be true/false, yes/no, or 1/0.")
                    continue
                is_active = parsed

            payload = {
                "name": name,
                "description": (row.get("description") or "").strip(),
                "default_notes": (row.get("default_notes") or "").strip(),
                "days_to_before_trip": days_to_before_trip,
                "sort_order": sort_order,
                "is_active": is_active,
            }
            template = TaskTemplate(**payload)
            try:
                template.full_clean(validate_unique=False)
            except ValidationError as exc:
                for field, field_errors in exc.message_dict.items():
                    for field_error in field_errors:
                        errors.append(f"Row {index}: {field} - {field_error}")
                continue
            payloads.append(payload)

        if errors:
            raise ValidationError(errors)
        return payloads

    def _parse_bool(self, value):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y"}:
            return True
        if normalized in {"0", "false", "no", "n"}:
            return False
        return None


@admin.register(WorkTaskTemplatePack)
class WorkTaskTemplatePackAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_active", "active_template_total")
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    filter_horizontal = ("task_templates",)

    @admin.display(description="Templates")
    def active_template_total(self, obj):
        return obj.active_template_count
