from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse


class AuthManagementAdminTests(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="password",
        )

    def test_admin_groups_roles_and_permissions_under_authentication_app(self):
        request = RequestFactory().get("/admin/")
        request.user = self.superuser

        auth_app = next(
            app
            for app in admin.site.get_app_list(request)
            if app["name"] == "Authentication"
        )

        self.assertEqual(
            [model["name"] for model in auth_app["models"]],
            ["Permissions", "Roles"],
        )

    def test_permission_matrix_updates_role_permissions(self):
        self.client.force_login(self.superuser)
        role = Group.objects.create(name="Trip Manager")
        permission = Permission.objects.get(codename="view_trip")

        response = self.client.post(
            reverse("admin:auth_management_rolepermission_changelist"),
            {f"role_{role.pk}_permission_{permission.pk}": "on"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(role.permissions.filter(pk=permission.pk).exists())
