from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse

from trips.models import Employee, Task, TaskTemplate, Trip, TripStatus


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
            ["Task Template Packs", "Task Templates", "Tasks"],
        )

    def test_admin_task_changelist_shows_import_csv_link(self):
        user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:work_tasks_worktask_changelist"))

        self.assertContains(response, reverse("admin:work_tasks_worktask_import_csv"))
        self.assertContains(response, "Import CSV")

    def test_admin_task_changelist_uses_compact_summary_columns(self):
        user = get_user_model().objects.create_superuser(
            email="admin-compact@example.com",
            password="password",
        )
        trip_owner = Employee.objects.create(
            user=get_user_model().objects.create_user(email="manager-compact@example.com")
        )
        assignee_user = get_user_model().objects.create_user(
            email="assignee@example.com",
            first_name="Ava",
            last_name="Stone",
        )
        assignee = Employee.objects.create(user=assignee_user)
        status = TripStatus.objects.create(name="Confirmed")
        trip = Trip.objects.create(
            name="Barcelona 2026",
            start_date="2026-09-10",
            end_date="2026-09-18",
            trip_manager=trip_owner,
            status=status,
        )
        Task.objects.create(
            name="Confirm rooming list",
            trip=trip,
            assigned_to=assignee,
            status=Task.Status.IN_PROGRESS,
            due_date="2026-08-15",
            notes="Reach out to the hotel and verify the final room split before payment.",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:work_tasks_worktask_changelist"))

        self.assertContains(response, "field-task_summary")
        self.assertContains(response, "field-assigned_summary")
        self.assertContains(response, "field-status_summary")
        self.assertContains(response, "field-due_summary")
        self.assertContains(response, "Trip: Barcelona 2026")
        self.assertContains(response, "Ava Stone")
        self.assertContains(response, "In Progress")
        self.assertNotContains(response, "field-source_template")

    def test_admin_can_import_tasks_from_csv(self):
        user = get_user_model().objects.create_superuser(
            email="admin2@example.com",
            password="password",
        )
        employee_user = get_user_model().objects.create_user(email="staff@example.com")
        employee = Employee.objects.create(user=employee_user)
        trip_owner = Employee.objects.create(user=get_user_model().objects.create_user(email="manager@example.com"))
        status = TripStatus.objects.create(name="Planning")
        trip = Trip.objects.create(
            name="Greece 2026",
            start_date="2026-09-10",
            end_date="2026-09-18",
            trip_manager=trip_owner,
            status=status,
        )
        self.client.force_login(user)

        csv_content = (
            "name,trip_id,assigned_to_email,status,due_date,days_to_before_trip,notes\n"
            f"Collect waivers,{trip.pk},staff@example.com,in_progress,2026-08-01,,Check for missing signatures\n"
        )
        upload = SimpleUploadedFile("tasks.csv", csv_content.encode("utf-8"), content_type="text/csv")

        response = self.client.post(
            reverse("admin:work_tasks_worktask_import_csv"),
            {"csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        task = Task.objects.get(name="Collect waivers")
        self.assertEqual(task.trip, trip)
        self.assertEqual(task.assigned_to, employee)
        self.assertEqual(task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(str(task.due_date), "2026-08-01")

    def test_admin_task_template_changelist_shows_import_csv_link(self):
        user = get_user_model().objects.create_superuser(
            email="admin3@example.com",
            password="password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:work_tasks_worktasktemplate_changelist"))

        self.assertContains(response, reverse("admin:work_tasks_worktasktemplate_import_csv"))
        self.assertContains(response, "Import CSV")

    def test_admin_can_import_task_templates_from_csv(self):
        user = get_user_model().objects.create_superuser(
            email="admin4@example.com",
            password="password",
        )
        self.client.force_login(user)

        csv_content = (
            "name,description,default_notes,days_to_before_trip,sort_order,is_active\n"
            "Collect Waivers,Waiver collection step,Review missing waivers,-45,7,true\n"
        )
        upload = SimpleUploadedFile(
            "task_templates.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("admin:work_tasks_worktasktemplate_import_csv"),
            {"csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        template = TaskTemplate.objects.get(name="Collect Waivers")
        self.assertEqual(template.description, "Waiver collection step")
        self.assertEqual(template.default_notes, "Review missing waivers")
        self.assertEqual(template.days_to_before_trip, -45)
        self.assertEqual(template.sort_order, 7)
        self.assertTrue(template.is_active)

    def test_admin_task_template_import_updates_existing_template_by_name(self):
        user = get_user_model().objects.create_superuser(
            email="admin5@example.com",
            password="password",
        )
        TaskTemplate.objects.create(
            name="Collect Waivers",
            description="Old description",
            default_notes="Old notes",
            days_to_before_trip=-30,
            sort_order=1,
            is_active=False,
        )
        self.client.force_login(user)

        csv_content = (
            "name,description,default_notes,days_to_before_trip,sort_order,is_active\n"
            "Collect Waivers,Updated description,Updated notes,-60,9,yes\n"
        )
        upload = SimpleUploadedFile(
            "task_templates.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("admin:work_tasks_worktasktemplate_import_csv"),
            {"csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        template = TaskTemplate.objects.get(name="Collect Waivers")
        self.assertEqual(template.description, "Updated description")
        self.assertEqual(template.default_notes, "Updated notes")
        self.assertEqual(template.days_to_before_trip, -60)
        self.assertEqual(template.sort_order, 9)
        self.assertTrue(template.is_active)
