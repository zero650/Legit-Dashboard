from django.contrib import admin

from .models import WorkTask, WorkTaskTemplate


@admin.register(WorkTask)
class WorkTaskAdmin(admin.ModelAdmin):
    list_display = ("name", "trip", "source_template", "assigned_to", "status", "due_date")
    list_filter = ("status", "assigned_to", "trip__status", "source_template")
    search_fields = ("name", "notes", "assigned_to__user__email")
    autocomplete_fields = ("trip",)


@admin.register(WorkTaskTemplate)
class WorkTaskTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "days_to_before_trip", "sort_order", "is_active")
    list_editable = ("days_to_before_trip", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description", "default_notes")
