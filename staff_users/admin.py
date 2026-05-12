from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from trips.models import Employee

from .forms import EmailUserChangeForm, EmailUserCreationForm
from .models import StaffEmployee, User


class EmployeeInline(admin.StackedInline):
    model = Employee
    can_delete = False
    filter_horizontal = ("roles",)
    verbose_name_plural = "employee profile"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = EmailUserChangeForm
    add_form = EmailUserCreationForm
    inlines = [EmployeeInline]
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active")
    list_filter = ("is_staff", "is_superuser", "is_active")
    ordering = ("email",)
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(StaffEmployee)
class StaffEmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "role_names")
    list_filter = ("roles",)
    search_fields = ("user__first_name", "user__last_name", "user__email")
    filter_horizontal = ("roles",)
