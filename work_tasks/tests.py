from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase


class WorkTasksAdminTests(TestCase):
    def test_admin_groups_tasks_and_templates_under_tasks_app(self):
        request = RequestFactory().get("/admin/")
        request.user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="password",
        )

        tasks_app = next(
            app
            for app in admin.site.get_app_list(request)
            if app["name"] == "Tasks"
        )

        self.assertEqual(
            [model["name"] for model in tasks_app["models"]],
            ["Task Templates", "Tasks"],
        )
