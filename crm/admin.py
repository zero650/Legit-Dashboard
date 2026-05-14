from django.contrib import admin

from .models import Customer, CustomerDocument, CustomerDocumentType, CustomerTripHistory


class CustomerDocumentInline(admin.TabularInline):
    model = CustomerDocument
    extra = 0
    fields = ("document_type", "title", "file", "notes", "uploaded_at")
    readonly_fields = ("uploaded_at",)


class CustomerTripHistoryInline(admin.TabularInline):
    model = CustomerTripHistory
    extra = 0
    fields = ("trip_name", "trip_start_date", "trip_end_date", "money_spent")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "email",
        "phone_number",
        "city",
        "state",
        "passport_expiration_date",
    )
    search_fields = (
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "city",
        "state",
        "postal",
        "passport_number",
        "notes",
    )
    list_filter = ("state", "passport_expiration_date")
    inlines = [CustomerTripHistoryInline, CustomerDocumentInline]


@admin.register(CustomerDocument)
class CustomerDocumentAdmin(admin.ModelAdmin):
    list_display = ("display_name", "document_type", "customer", "uploaded_at")
    search_fields = (
        "title",
        "document_type__name",
        "customer__first_name",
        "customer__last_name",
        "customer__email",
    )
    list_filter = ("document_type", "uploaded_at")


@admin.register(CustomerDocumentType)
class CustomerDocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name", "description")
    list_filter = ("is_active",)


@admin.register(CustomerTripHistory)
class CustomerTripHistoryAdmin(admin.ModelAdmin):
    list_display = ("trip_name", "customer", "trip_start_date", "trip_end_date", "money_spent")
    search_fields = ("trip_name", "customer__first_name", "customer__last_name", "customer__email")
    list_filter = ("trip_start_date", "trip_end_date")
