from django.contrib import admin

from .models import Task, Trip, TripStatus


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

    @admin.display(description="Open tasks")
    def open_task_total(self, obj):
        return obj.open_tasks_count
