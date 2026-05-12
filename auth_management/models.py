from django.contrib.auth.models import Group, Permission


class Role(Group):
    class Meta:
        proxy = True
        verbose_name = "Role"
        verbose_name_plural = "Roles"


class RolePermission(Permission):
    class Meta:
        proxy = True
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"

