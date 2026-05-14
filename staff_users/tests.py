from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse


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
