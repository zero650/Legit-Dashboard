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

from .models import Employee, Task, Trip, TripStatus


class TripCsvImportForm(forms.Form):
    csv_file = forms.FileField(
        help_text=(
            "CSV columns: name, start_date, end_date, trip_manager_email, "
            "status, trip_leader_email, notes"
        )
    )


@admin.register(TripStatus)
class TripStatusAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name",)


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = (
        "name",
        "source_template",
        "assigned_to",
        "status",
        "due_date",
        "days_to_before_trip",
    )
    readonly_fields = ("source_template",)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "start_date",
        "end_date",
        "trip_manager",
        "trip_leader",
        "status",
        "open_task_total",
    )
    list_filter = ("status", "trip_manager")
    search_fields = (
        "name",
        "trip_leader__user__first_name",
        "trip_leader__user__last_name",
        "trip_leader__user__email",
        "notes",
        "trip_manager__user__email",
    )
    date_hierarchy = "start_date"
    inlines = [TaskInline]
    change_list_template = "admin/trips/trip/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="trips_trip_import_csv",
            ),
        ]
        return custom_urls + urls

    def import_csv_view(self, request):
        form = TripCsvImportForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            csv_file = form.cleaned_data["csv_file"]
            decoded = csv_file.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(decoded))

            required_columns = {"name", "start_date", "end_date", "trip_manager_email", "status"}
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
                trips_to_create = self._build_trips_from_csv(reader)
            except ValidationError as exc:
                for message in exc.messages:
                    self.message_user(request, message, level=messages.ERROR)
                return HttpResponseRedirect(request.path)

            with transaction.atomic():
                for trip in trips_to_create:
                    trip.save()

            self.message_user(
                request,
                f"Imported {len(trips_to_create)} trips successfully.",
                level=messages.SUCCESS,
            )
            return HttpResponseRedirect(reverse("admin:trips_trip_changelist"))

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "form": form,
            "title": "Import Trips from CSV",
        }
        return render(request, "admin/trips/trip/import_csv.html", context)

    def _build_trips_from_csv(self, reader):
        trips = []
        errors = []
        valid_manager_ids = set(
            Employee.objects.filter(roles__name__in=["Administrator", "Staff"]).values_list("id", flat=True)
        )
        valid_leader_ids = set(
            Employee.objects.filter(roles__name="Host").values_list("id", flat=True)
        )
        status_map = {
            status.name.lower(): status
            for status in TripStatus.objects.filter(is_active=True)
        }

        for index, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue

            start_date = parse_date((row.get("start_date") or "").strip())
            end_date = parse_date((row.get("end_date") or "").strip())
            if start_date is None:
                errors.append(f"Row {index}: start_date must be in YYYY-MM-DD format.")
                continue
            if end_date is None:
                errors.append(f"Row {index}: end_date must be in YYYY-MM-DD format.")
                continue

            manager_email = (row.get("trip_manager_email") or "").strip()
            manager = Employee.objects.filter(user__email__iexact=manager_email).first()
            if not manager:
                errors.append(f"Row {index}: trip_manager_email {manager_email} was not found.")
                continue
            if manager.pk not in valid_manager_ids:
                errors.append(f"Row {index}: {manager_email} is not eligible to be a trip manager.")
                continue

            status_name = (row.get("status") or "").strip().lower()
            status = status_map.get(status_name)
            if not status:
                errors.append(f"Row {index}: status must match an active trip status.")
                continue

            leader = None
            leader_email = (row.get("trip_leader_email") or "").strip()
            if leader_email:
                leader = Employee.objects.filter(user__email__iexact=leader_email).first()
                if not leader:
                    errors.append(f"Row {index}: trip_leader_email {leader_email} was not found.")
                    continue
                if leader.pk not in valid_leader_ids:
                    errors.append(f"Row {index}: {leader_email} is not eligible to be a trip leader.")
                    continue

            trip = Trip(
                name=(row.get("name") or "").strip(),
                start_date=start_date,
                end_date=end_date,
                trip_manager=manager,
                status=status,
                trip_leader=leader,
                notes=(row.get("notes") or "").strip(),
            )
            try:
                trip.full_clean()
            except ValidationError as exc:
                for field, field_errors in exc.message_dict.items():
                    for field_error in field_errors:
                        errors.append(f"Row {index}: {field} - {field_error}")
                continue

            trips.append(trip)

        if errors:
            raise ValidationError(errors)
        return trips

    @admin.display(description="Open tasks")
    def open_task_total(self, obj):
        return obj.open_tasks_count
