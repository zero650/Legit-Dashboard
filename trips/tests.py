from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .forms import TripForm
from .models import Employee, Task, TaskTemplate, Trip, TripStatus


class TripModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="manager@example.com",
            first_name="Trip",
            last_name="Manager",
        )
        self.employee = Employee.objects.create(user=self.user)
        staff_role, _ = Group.objects.get_or_create(name="Staff")
        self.employee.roles.add(staff_role)
        self.status = TripStatus.objects.create(name="Planning")

    def test_trip_end_date_must_not_precede_start_date(self):
        trip = Trip(
            name="Costa Rica 2026",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 5),
            trip_manager=self.employee,
            status=self.status,
        )

        with self.assertRaises(ValidationError):
            trip.full_clean()

    def test_task_due_date_can_be_calculated_from_days_before_trip(self):
        trip = Trip.objects.create(
            name="Costa Rica 2026",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 17),
            trip_manager=self.employee,
            status=self.status,
        )

        task = Task.objects.create(
            name="Collect rooming list",
            trip=trip,
            days_to_before_trip=-30,
        )

        self.assertEqual(task.due_date, date(2026, 6, 10))

    def test_positive_day_offset_is_after_trip_start(self):
        trip = Trip.objects.create(
            name="Costa Rica 2026",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 17),
            trip_manager=self.employee,
            status=self.status,
        )

        task = Task.objects.create(
            name="Request Reviews",
            trip=trip,
            days_to_before_trip=1,
        )

        self.assertEqual(task.due_date, date(2026, 7, 11))

    def test_trip_can_apply_task_templates_once(self):
        trip = Trip.objects.create(
            name="Costa Rica 2026",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 17),
            trip_manager=self.employee,
            status=self.status,
        )
        TaskTemplate.objects.create(
            name="Collect rooming list",
            days_to_before_trip=-30,
        )
        TaskTemplate.objects.create(
            name="Inactive template",
            days_to_before_trip=-10,
            is_active=False,
        )

        self.assertEqual(
            trip.apply_task_templates(
                assigned_to=self.employee,
                status=Task.Status.IN_PROGRESS,
            ),
            1,
        )
        self.assertEqual(trip.apply_task_templates(), 0)

        task = trip.tasks.get(name="Collect rooming list")
        self.assertEqual(task.due_date, date(2026, 6, 10))
        self.assertEqual(task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(task.assigned_to, self.employee)
        self.assertEqual(trip.tasks.count(), 1)

    def test_employee_roles_are_django_groups(self):
        group = Group.objects.create(name="Trip Manager")
        user = get_user_model().objects.create_user(email="trip-manager@example.com")

        employee = Employee.objects.create(user=user)
        employee.roles.add(group)

        self.assertEqual(employee.role_names, "Trip Manager")
        self.assertTrue(user.groups.filter(name="Trip Manager").exists())

    def test_trip_form_limits_trip_leader_to_host_employees(self):
        host_role, _ = Group.objects.get_or_create(name="Host")
        host_user = get_user_model().objects.create_user(
            email="host@example.com",
            first_name="Trip",
            last_name="Host",
        )
        host_employee = Employee.objects.create(user=host_user)
        host_employee.roles.add(host_role)
        non_host_user = get_user_model().objects.create_user(
            email="staff@example.com",
            first_name="Staff",
            last_name="Member",
        )
        non_host_employee = Employee.objects.create(user=non_host_user)

        form = TripForm()

        self.assertIn(host_employee, form.fields["trip_leader"].queryset)
        self.assertNotIn(non_host_employee, form.fields["trip_leader"].queryset)

    def test_trip_form_limits_trip_manager_to_staff_and_administrators(self):
        staff_role, _ = Group.objects.get_or_create(name="Staff")
        administrator_role, _ = Group.objects.get_or_create(name="Administrator")
        host_role, _ = Group.objects.get_or_create(name="Host")
        staff_user = get_user_model().objects.create_user(email="staff@example.com")
        staff_employee = Employee.objects.create(user=staff_user)
        staff_employee.roles.add(staff_role)
        administrator_user = get_user_model().objects.create_user(email="admin@example.com")
        administrator_employee = Employee.objects.create(user=administrator_user)
        administrator_employee.roles.add(administrator_role)
        host_user = get_user_model().objects.create_user(email="host-only@example.com")
        host_employee = Employee.objects.create(user=host_user)
        host_employee.roles.add(host_role)

        form = TripForm()

        self.assertIn(staff_employee, form.fields["trip_manager"].queryset)
        self.assertIn(administrator_employee, form.fields["trip_manager"].queryset)
        self.assertNotIn(host_employee, form.fields["trip_manager"].queryset)

    def test_trip_form_limits_status_to_active_statuses(self):
        inactive_status = TripStatus.objects.create(name="Lead", is_active=False)

        form = TripForm()

        self.assertIn(self.status, form.fields["status"].queryset)
        self.assertNotIn(inactive_status, form.fields["status"].queryset)


class TripCreateAndTaskTemplateViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="creator@example.com",
            password="password",
            is_staff=True,
        )
        self.user.user_permissions.add(
            *Permission.objects.filter(codename__in=["add_trip", "add_task", "view_trip"])
        )
        self.employee = Employee.objects.create(user=self.user)
        staff_role, _ = Group.objects.get_or_create(name="Staff")
        self.employee.roles.add(staff_role)
        self.status = TripStatus.objects.create(name="Planning")

    def test_trip_create_sets_created_by_to_current_employee(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("trip_create"),
            {
                "name": "Costa Rica 2026",
                "start_date": "2026-07-10",
                "end_date": "2026-07-17",
                "trip_manager": self.employee.pk,
                "status": self.status.pk,
                "trip_leader": "",
                "notes": "",
            },
        )

        trip = Trip.objects.get()
        self.assertRedirects(response, trip.get_absolute_url())
        self.assertEqual(trip.created_by, self.employee)

    def test_add_all_tasks_assigns_templates_to_trip_creator_in_progress(self):
        self.client.force_login(self.user)
        trip = Trip.objects.create(
            name="Costa Rica 2026",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 17),
            trip_manager=self.employee,
            created_by=self.employee,
            status=self.status,
        )
        first_template = TaskTemplate.objects.create(
            name="Itinerary/Pricing Confirmed",
            days_to_before_trip=-365,
        )
        second_template = TaskTemplate.objects.create(
            name="Trip Page for Website",
            days_to_before_trip=-365,
        )
        TaskTemplate.objects.create(
            name="Inactive",
            days_to_before_trip=-30,
            is_active=False,
        )

        response = self.client.post(reverse("trip_apply_task_templates", args=[trip.pk]))

        self.assertRedirects(response, trip.get_absolute_url())
        self.assertEqual(trip.tasks.count(), 2)
        for template in [first_template, second_template]:
            task = trip.tasks.get(source_template=template)
            self.assertEqual(task.assigned_to, self.employee)
            self.assertEqual(task.status, Task.Status.IN_PROGRESS)

    def test_add_all_tasks_falls_back_to_trip_manager_when_created_by_missing(self):
        self.client.force_login(self.user)
        trip = Trip.objects.create(
            name="Costa Rica 2026",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 17),
            trip_manager=self.employee,
            status=self.status,
        )
        template = TaskTemplate.objects.create(
            name="Itinerary/Pricing Confirmed",
            days_to_before_trip=-365,
        )

        self.client.post(reverse("trip_apply_task_templates", args=[trip.pk]))

        task = trip.tasks.get(source_template=template)
        self.assertEqual(task.assigned_to, self.employee)
        self.assertEqual(task.status, Task.Status.IN_PROGRESS)


class TaskCreateViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="password",
            is_staff=True,
        )
        self.user.user_permissions.add(
            *self._permissions("add_task", "view_trip", "view_tasktemplate")
        )
        self.employee = Employee.objects.create(user=self.user)
        self.status = TripStatus.objects.create(name="Planning")
        self.trip = Trip.objects.create(
            name="Costa Rica 2026",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 17),
            trip_manager=self.employee,
            status=self.status,
        )
        self.template = TaskTemplate.objects.create(
            name="Collect rooming list",
            default_notes="Ask host for final rooming assignments.",
            days_to_before_trip=-30,
        )

    def _permissions(self, *codenames):
        from django.contrib.auth.models import Permission

        return Permission.objects.filter(codename__in=codenames)

    def test_create_task_form_uses_template_instead_of_custom_name(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_create"))

        self.assertContains(response, "Task template")
        self.assertContains(response, self.template.name)
        self.assertNotContains(response, 'name="name"')

    def test_create_task_from_template_sets_name_notes_and_due_date(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_create"),
            {
                "source_template": self.template.pk,
                "trip": self.trip.pk,
                "assigned_to": self.employee.pk,
                "status": Task.Status.NOT_STARTED,
                "due_date": "",
                "days_to_before_trip": "",
                "notes": "",
            },
        )

        task = Task.objects.get()
        self.assertRedirects(response, self.trip.get_absolute_url())
        self.assertEqual(task.name, self.template.name)
        self.assertEqual(task.notes, self.template.default_notes)
        self.assertEqual(task.days_to_before_trip, -30)
        self.assertEqual(task.due_date, date(2026, 6, 10))


class TaskTemplateStaffPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="templates@example.com",
            password="password",
            is_staff=True,
        )
        self.user.user_permissions.add(
            *self._permissions(
                "view_tasktemplate",
                "change_tasktemplate",
                "delete_tasktemplate",
            )
        )
        self.first_template = TaskTemplate.objects.create(
            name="First",
            sort_order=1,
        )
        self.second_template = TaskTemplate.objects.create(
            name="Second",
            sort_order=2,
        )

    def _permissions(self, *codenames):
        from django.contrib.auth.models import Permission

        return Permission.objects.filter(codename__in=codenames)

    def test_task_template_list_has_delete_and_drag_controls(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_template_list"))

        self.assertContains(response, "Drag to reorder")
        self.assertContains(response, reverse("task_template_delete", args=[self.first_template.pk]))
        self.assertContains(response, "Delete")

    def test_staff_can_delete_task_template(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_template_delete", args=[self.first_template.pk])
        )

        self.assertRedirects(response, reverse("task_template_list"))
        self.assertFalse(TaskTemplate.objects.filter(pk=self.first_template.pk).exists())

    def test_staff_can_reorder_task_templates(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_template_reorder"),
            {
                "template_ids[]": [
                    str(self.second_template.pk),
                    str(self.first_template.pk),
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.first_template.refresh_from_db()
        self.second_template.refresh_from_db()
        self.assertEqual(self.second_template.sort_order, 1)
        self.assertEqual(self.first_template.sort_order, 2)


class SeedLegitDefaultsTests(TestCase):
    def test_seed_creates_expected_default_roles(self):
        call_command("seed_legit_defaults", verbosity=0)

        self.assertTrue(Group.objects.filter(name="Administrator").exists())
        self.assertTrue(Group.objects.filter(name="Staff").exists())
        self.assertTrue(Group.objects.filter(name="Host").exists())
        self.assertFalse(Group.objects.filter(name="Operations Manager").exists())
        self.assertFalse(Group.objects.filter(name="Trip Manager").exists())

    def test_seed_activates_only_current_trip_statuses(self):
        TripStatus.objects.create(name="Lead", is_active=True)

        call_command("seed_legit_defaults", verbosity=0)

        active_statuses = set(
            TripStatus.objects.filter(is_active=True).values_list("name", flat=True)
        )
        self.assertEqual(active_statuses, {"Completed", "Closed", "Planning", "On Sale"})
        self.assertFalse(TripStatus.objects.get(name="Lead").is_active)

    def test_seed_renames_legacy_roles(self):
        user = get_user_model().objects.create_user(email="legacy@example.com")
        employee = Employee.objects.create(user=user)
        legacy_admin = Group.objects.create(name="Operations Manager")
        legacy_manager = Group.objects.create(name="Trip Manager")
        user.groups.add(legacy_admin, legacy_manager)
        employee.roles.add(legacy_admin, legacy_manager)

        call_command("seed_legit_defaults", verbosity=0)

        self.assertTrue(user.groups.filter(name="Administrator").exists())
        self.assertTrue(user.groups.filter(name="Staff").exists())
        self.assertTrue(employee.roles.filter(name="Administrator").exists())
        self.assertTrue(employee.roles.filter(name="Staff").exists())
        self.assertFalse(Group.objects.filter(name="Operations Manager").exists())
        self.assertFalse(Group.objects.filter(name="Trip Manager").exists())
