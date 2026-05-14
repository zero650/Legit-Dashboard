from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.contrib.auth.models import Group, Permission

from trips.models import Employee


class StaffUsersAdminTests(TestCase):
    def test_user_model_uses_email_without_username(self):
        user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="password",
        )

        self.assertEqual(user.get_username(), "staff@example.com")
        self.assertNotIn("username", [field.name for field in user._meta.fields])

    def test_admin_groups_only_users_under_users_app(self):
        request = RequestFactory().get("/admin/")
        request.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="password",
        )

        users_app = next(
            app
            for app in admin.site.get_app_list(request)
            if app["name"] == "Users"
        )

        self.assertEqual([model["name"] for model in users_app["models"]], ["Users"])

    def test_admin_add_user_form_uses_email_field(self):
        self.client.force_login(
            get_user_model().objects.create_superuser(
                email="admin@example.com",
                password="password",
            )
        )

        response = self.client.get(reverse("admin:staff_users_user_add"))

        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'name="username"')
        self.assertNotContains(response, 'name="groups"')


class StaffUsersViewTests(TestCase):
    def setUp(self):
        self.staff_role = Group.objects.create(name="Staff")
        self.host_role = Group.objects.create(name="Host")
        self.admin_user = get_user_model().objects.create_user(
            email="manager@example.com",
            password="password",
            first_name="Mina",
            last_name="Manager",
        )
        self.admin_user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["view_user", "add_user", "change_user", "view_trip"]
            )
        )
        self.admin_employee = Employee.objects.create(user=self.admin_user)
        self.admin_employee.roles.add(self.staff_role)

    def test_authenticated_navigation_shows_staff_link(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("trip_dashboard"))

        self.assertContains(response, reverse("staff_list"))
        self.assertContains(response, ">Staff<", html=False)

    def test_staff_list_displays_users_and_roles(self):
        host_user = get_user_model().objects.create_user(
            email="host@example.com",
            first_name="Holly",
            last_name="Host",
        )
        host_employee = Employee.objects.create(user=host_user)
        host_employee.roles.add(self.host_role)
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("staff_list"))

        self.assertContains(response, "Holly Host")
        self.assertContains(response, "host@example.com")
        self.assertContains(response, "Host")

    def test_staff_create_builds_user_and_employee_profile(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("staff_create"),
            {
                "email": "newstaff@example.com",
                "first_name": "Nina",
                "last_name": "North",
                "is_active": "on",
                "is_staff": "on",
                "roles": [self.staff_role.pk, self.host_role.pk],
                "password1": "strong-password-123",
                "password2": "strong-password-123",
            },
        )

        self.assertRedirects(response, reverse("staff_list"))
        created_user = get_user_model().objects.get(email="newstaff@example.com")
        self.assertTrue(created_user.check_password("strong-password-123"))
        self.assertTrue(created_user.is_staff)
        self.assertEqual(created_user.get_full_name(), "Nina North")
        self.assertTrue(hasattr(created_user, "employee_profile"))
        self.assertEqual(
            set(created_user.employee_profile.roles.values_list("name", flat=True)),
            {"Host", "Staff"},
        )
        self.assertEqual(
            set(created_user.groups.values_list("name", flat=True)),
            {"Host", "Staff"},
        )

    def test_staff_update_changes_roles_and_password(self):
        existing_user = get_user_model().objects.create_user(
            email="existing@example.com",
            password="old-password",
            first_name="Eli",
            last_name="Existing",
        )
        existing_employee = Employee.objects.create(user=existing_user)
        existing_employee.roles.add(self.staff_role)
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("staff_update", args=[existing_user.pk]),
            {
                "email": "existing@example.com",
                "first_name": "Elena",
                "last_name": "Existing",
                "is_active": "on",
                "roles": [self.host_role.pk],
                "password1": "new-password-456",
                "password2": "new-password-456",
            },
        )

        self.assertRedirects(response, reverse("staff_list"))
        existing_user.refresh_from_db()
        self.assertEqual(existing_user.first_name, "Elena")
        self.assertFalse(existing_user.is_staff)
        self.assertTrue(existing_user.check_password("new-password-456"))
        self.assertEqual(
            list(existing_user.employee_profile.roles.values_list("name", flat=True)),
            ["Host"],
        )
        self.assertEqual(
            list(existing_user.groups.values_list("name", flat=True)),
            ["Host"],
        )
