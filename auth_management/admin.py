from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse

from .models import Role, RolePermission


@admin.register(Role)
class RoleAdmin(BaseGroupAdmin):
    pass


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    change_list_template = "admin/auth_management/permission_matrix.html"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied

        roles = list(Group.objects.prefetch_related("permissions").order_by("name"))
        permissions = list(
            RolePermission.objects.select_related("content_type").order_by(
                "content_type__app_label",
                "content_type__model",
                "codename",
            )
        )

        if request.method == "POST":
            if not request.user.has_perm("auth_management.change_rolepermission"):
                raise PermissionDenied

            for role in roles:
                selected_permission_ids = [
                    permission.pk
                    for permission in permissions
                    if request.POST.get(f"role_{role.pk}_permission_{permission.pk}")
                ]
                role.permissions.set(selected_permission_ids)

            self.message_user(request, "Role permissions updated.", messages.SUCCESS)

        role_permission_ids = {
            role.pk: set(role.permissions.values_list("pk", flat=True))
            for role in roles
        }
        permission_rows = [
            {
                "permission": permission,
                "label": f"{permission.content_type.app_label}.{permission.codename}",
                "roles": [
                    {
                        "role": role,
                        "checked": permission.pk in role_permission_ids[role.pk],
                        "field_name": f"role_{role.pk}_permission_{permission.pk}",
                    }
                    for role in roles
                ],
            }
            for permission in permissions
        ]

        context = {
            **self.admin_site.each_context(request),
            "title": "Permissions",
            "opts": self.model._meta,
            "roles": roles,
            "permission_rows": permission_rows,
            "has_change_permission": request.user.has_perm("auth_management.change_rolepermission"),
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
        }
        if extra_context:
            context.update(extra_context)

        return TemplateResponse(request, self.change_list_template, context)


admin.site.unregister(Group)
