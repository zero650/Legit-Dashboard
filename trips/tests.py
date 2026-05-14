from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from crm.models import Customer, CustomerTripHistory

from .forms import TripForm
from .models import Employee, Task, TaskTemplate, TaskTemplatePack, Trip, TripStatus


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

    def test_due_in_display_shows_done_for_completed_tasks(self):
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
            due_date=date(2026, 1, 1),
            status=Task.Status.DONE,
        )

        self.assertEqual(task.due_in_display, "Done")

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

    def test_add_task_pack_adds_only_templates_in_selected_pack(self):
        self.client.force_login(self.user)
        trip = Trip.objects.create(
            name="Costa Rica 2026",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 17),
            trip_manager=self.employee,
            created_by=self.employee,
            status=self.status,
        )
        included = TaskTemplate.objects.create(
            name="Included Template",
            days_to_before_trip=-30,
        )
        excluded = TaskTemplate.objects.create(
            name="Excluded Template",
            days_to_before_trip=-20,
        )
        pack = TaskTemplatePack.objects.create(name="Website Trips")
        pack.task_templates.add(included)

        response = self.client.post(
            reverse("trip_apply_task_templates", args=[trip.pk]),
            {"task_template_pack": pack.pk},
        )

        self.assertRedirects(response, trip.get_absolute_url())
        self.assertTrue(trip.tasks.filter(source_template=included).exists())
        self.assertFalse(trip.tasks.filter(source_template=excluded).exists())

    def test_add_task_pack_preserves_negative_day_offsets_in_due_dates(self):
        self.client.force_login(self.user)
        trip = Trip.objects.create(
            name="June 2026 Website Trip",
            start_date=date(2026, 6, 12),
            end_date=date(2026, 6, 19),
            trip_manager=self.employee,
            created_by=self.employee,
            status=self.status,
        )
        template = TaskTemplate.objects.create(
            name="Trip Page for Website",
            days_to_before_trip=-365,
        )
        pack = TaskTemplatePack.objects.create(name="Website Launch")
        pack.task_templates.add(template)

        response = self.client.post(
            reverse("trip_apply_task_templates", args=[trip.pk]),
            {"task_template_pack": pack.pk},
        )

        task = trip.tasks.get(source_template=template)
        self.assertRedirects(response, trip.get_absolute_url())
        self.assertEqual(task.days_to_before_trip, -365)
        self.assertEqual(task.due_date, date(2025, 6, 12))


class TripDashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="dashboard@example.com",
            password="password",
        )
        self.employee = Employee.objects.create(user=self.user)
        staff_role, _ = Group.objects.get_or_create(name="Staff")
        self.employee.roles.add(staff_role)
        self.status = TripStatus.objects.create(name="Planning")

    def test_dashboard_shows_running_trip_count_and_add_task_links(self):
        today = timezone.localdate()
        running_status = TripStatus.objects.create(name="On Sale", is_active=True)
        completed_status = TripStatus.objects.create(name="Completed", is_active=True)
        running_trip = Trip.objects.create(
            name="Running Trip",
            start_date=today,
            end_date=today,
            trip_manager=self.employee,
            status=running_status,
        )
        Trip.objects.create(
            name="Completed Trip",
            start_date=today,
            end_date=today,
            trip_manager=self.employee,
            status=completed_status,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("trip_dashboard"))

        self.assertContains(response, "Currently running trips")
        self.assertEqual(response.context["running_trip_count"], 1)
        self.assertContains(response, f'{reverse("task_create")}?trip={running_trip.pk}')
        self.assertNotContains(response, "Active task templates")
        self.assertNotContains(response, "Create task")

    def test_dashboard_shows_top_five_customers_by_trip_count(self):
        for index in range(6):
            customer = Customer.objects.create(
                first_name=f"Customer{index}",
                last_name="Traveler",
                email=f"customer{index}@example.com",
            )
            for trip_index in range(index + 1):
                CustomerTripHistory.objects.create(
                    customer=customer,
                    trip_name=f"Trip {trip_index}",
                    trip_start_date="2026-01-01",
                    trip_end_date="2026-01-07",
                    money_spent="1000.00",
                )

        self.client.force_login(self.user)
        response = self.client.get(reverse("trip_dashboard"))

        self.assertContains(response, "Top customers")
        self.assertContains(response, "Customer5 Traveler")
        self.assertContains(response, "Customer1 Traveler")
        self.assertNotContains(response, "Customer0 Traveler")


class TripListQuickUpdateTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="triplist@example.com",
            password="password",
            is_staff=True,
        )
        self.user.user_permissions.add(
            *Permission.objects.filter(codename__in=["change_trip"])
        )
        self.staff_role, _ = Group.objects.get_or_create(name="Staff")
        self.admin_role, _ = Group.objects.get_or_create(name="Administrator")
        self.host_role, _ = Group.objects.get_or_create(name="Host")

        self.manager_user = get_user_model().objects.create_user(email="manager1@example.com")
        self.manager_employee = Employee.objects.create(user=self.manager_user)
        self.manager_employee.roles.add(self.staff_role)

        self.second_manager_user = get_user_model().objects.create_user(email="manager2@example.com")
        self.second_manager_employee = Employee.objects.create(user=self.second_manager_user)
        self.second_manager_employee.roles.add(self.admin_role)

        self.host_user = get_user_model().objects.create_user(email="host1@example.com")
        self.host_employee = Employee.objects.create(user=self.host_user)
        self.host_employee.roles.add(self.host_role)

        self.second_host_user = get_user_model().objects.create_user(email="host2@example.com")
        self.second_host_employee = Employee.objects.create(user=self.second_host_user)
        self.second_host_employee.roles.add(self.host_role)

        self.status = TripStatus.objects.create(name="Planning")
        self.second_status = TripStatus.objects.create(name="On Sale", is_active=True)
        self.trip = Trip.objects.create(
            name="Japan 2026",
            start_date=date(2026, 9, 10),
            end_date=date(2026, 9, 17),
            trip_manager=self.manager_employee,
            trip_leader=self.host_employee,
            status=self.status,
        )
        self.other_trip = Trip.objects.create(
            name="Italy Dolomites",
            start_date=date(2026, 6, 12),
            end_date=date(2026, 6, 19),
            trip_manager=self.second_manager_employee,
            trip_leader=self.second_host_employee,
            status=self.second_status,
        )

    def test_trip_list_shows_inline_manager_and_leader_dropdowns(self):
        self.client.force_login(self.user)
        Task.objects.create(
            name="Open task",
            trip=self.trip,
            assigned_to=self.manager_employee,
            status=Task.Status.NOT_STARTED,
        )
        Task.objects.create(
            name="Closed task",
            trip=self.trip,
            assigned_to=self.manager_employee,
            status=Task.Status.DONE,
        )

        response = self.client.get(reverse("trip_list"))

        self.assertContains(response, reverse("trip_quick_update", args=[self.trip.pk]))
        self.assertContains(response, 'name="trip_leader"')
        self.assertContains(response, 'name="trip_manager"')
        self.assertContains(response, 'name="status"')
        self.assertContains(response, 'name="q"')
        self.assertContains(response, "Apply filters")
        self.assertContains(response, "Open Tasks")
        self.assertContains(response, ">1<", html=False)
        self.assertNotContains(response, "Trip ID")
        self.assertContains(response, self.second_manager_employee.email)
        self.assertContains(response, self.second_host_employee.email)
        self.assertContains(response, self.second_status.name)

    def test_trip_list_filters_and_search(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("trip_list"),
            {
                "q": "Italy",
                "status": self.second_status.pk,
                "trip_manager": self.second_manager_employee.pk,
                "trip_leader": self.second_host_employee.pk,
            },
        )

        self.assertContains(response, self.other_trip.name)
        self.assertNotContains(response, self.trip.name)

    def test_trip_list_quick_update_redirect_preserves_filters(self):
        self.client.force_login(self.user)
        next_url = (
            f"{reverse('trip_list')}?q=Japan&status={self.status.pk}"
            f"&trip_manager={self.manager_employee.pk}&trip_leader={self.host_employee.pk}"
        )

        response = self.client.post(
            reverse("trip_quick_update", args=[self.trip.pk]),
            {
                "trip_leader": self.second_host_employee.pk,
                "trip_manager": self.manager_employee.pk,
                "status": self.status.pk,
                "next": next_url,
            },
        )

        self.assertRedirects(response, next_url)

    def test_trip_list_can_quick_update_leader_without_overwriting_manager(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("trip_quick_update", args=[self.trip.pk]),
            {
                "trip_leader": self.second_host_employee.pk,
                "trip_manager": self.manager_employee.pk,
                "status": self.status.pk,
                "next": reverse("trip_list"),
            },
        )

        self.assertRedirects(response, reverse("trip_list"))
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.trip_leader, self.second_host_employee)
        self.assertEqual(self.trip.trip_manager, self.manager_employee)

    def test_trip_list_can_quick_update_manager_without_overwriting_leader(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("trip_quick_update", args=[self.trip.pk]),
            {
                "trip_leader": self.host_employee.pk,
                "trip_manager": self.second_manager_employee.pk,
                "status": self.status.pk,
                "next": reverse("trip_list"),
            },
        )

        self.assertRedirects(response, reverse("trip_list"))
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.trip_manager, self.second_manager_employee)
        self.assertEqual(self.trip.trip_leader, self.host_employee)

    def test_trip_list_can_quick_update_status_without_overwriting_leader_or_manager(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("trip_quick_update", args=[self.trip.pk]),
            {
                "trip_leader": self.host_employee.pk,
                "trip_manager": self.manager_employee.pk,
                "status": self.second_status.pk,
                "next": reverse("trip_list"),
            },
        )

        self.assertRedirects(response, reverse("trip_list"))
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, self.second_status)
        self.assertEqual(self.trip.trip_manager, self.manager_employee)
        self.assertEqual(self.trip.trip_leader, self.host_employee)

    def test_trip_list_quick_update_can_return_json_for_inline_save(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("trip_quick_update", args=[self.trip.pk]),
            {
                "trip_leader": self.second_host_employee.pk,
                "trip_manager": self.manager_employee.pk,
                "status": self.second_status.pk,
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["trip"]["status_id"], self.second_status.pk)
        self.assertEqual(response.json()["trip"]["status_label"], self.second_status.name)
        self.assertEqual(response.json()["trip"]["trip_leader"], str(self.second_host_employee))
        self.assertEqual(response.json()["trip"]["trip_manager"], str(self.manager_employee))
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, self.second_status)
        self.assertEqual(self.trip.trip_leader, self.second_host_employee)


class TaskDashboardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="taskdash@example.com",
            password="password",
            is_staff=True,
        )
        self.user.user_permissions.add(
            *Permission.objects.filter(codename__in=["change_task"])
        )
        self.employee = Employee.objects.create(user=self.user)
        staff_role, _ = Group.objects.get_or_create(name="Staff")
        self.employee.roles.add(staff_role)
        self.second_user = get_user_model().objects.create_user(
            email="othertask@example.com",
            password="password",
        )
        self.second_employee = Employee.objects.create(user=self.second_user)
        self.second_employee.roles.add(staff_role)
        self.status = TripStatus.objects.create(name="Planning")
        self.trip = Trip.objects.create(
            name="Italy 2026",
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 17),
            trip_manager=self.employee,
            status=self.status,
        )
        self.first_task = Task.objects.create(
            name="Send rooming reminder",
            trip=self.trip,
            assigned_to=self.employee,
            status=Task.Status.NOT_STARTED,
            due_date=date(2026, 7, 1),
        )
        self.second_task = Task.objects.create(
            name="Confirm host call",
            trip=self.trip,
            assigned_to=self.second_employee,
            status=Task.Status.DONE,
            due_date=date(2026, 7, 15),
        )

    def test_task_dashboard_shows_filters_and_inline_edit_controls(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_list"))

        self.assertContains(response, "Assigned to")
        self.assertContains(response, "Due date from")
        self.assertContains(response, reverse("task_quick_update", args=[self.first_task.pk]))
        self.assertContains(response, self.trip.name)

    def test_task_dashboard_filters_by_assignee_status_and_due_date(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("task_list"),
            {
                "assigned_to": self.second_employee.pk,
                "status": Task.Status.DONE,
                "due_date_from": "2026-07-10",
                "due_date_to": "2026-07-20",
            },
        )

        self.assertContains(response, self.second_task.name)
        self.assertNotContains(response, self.first_task.name)

    def test_task_dashboard_can_quick_update_task_and_return_to_filtered_page(self):
        self.client.force_login(self.user)
        self.first_task.days_to_before_trip = -30
        self.first_task.save()
        next_url = f"{reverse('task_list')}?status={Task.Status.NOT_STARTED}"

        response = self.client.post(
            reverse("task_quick_update", args=[self.first_task.pk]),
            {
                "assigned_to": self.second_employee.pk,
                "status": Task.Status.IN_PROGRESS,
                "due_date": "2026-07-20",
                "next": next_url,
            },
        )

        self.assertRedirects(response, next_url)
        self.first_task.refresh_from_db()
        self.assertEqual(self.first_task.assigned_to, self.second_employee)
        self.assertEqual(self.first_task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(self.first_task.due_date, date(2026, 7, 20))
        self.assertIsNone(self.first_task.days_to_before_trip)


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
        self.assertContains(response, 'name="name"')

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

    def test_create_one_off_task_without_template(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_create"),
            {
                "name": "Custom airport handoff",
                "source_template": "",
                "trip": self.trip.pk,
                "assigned_to": self.employee.pk,
                "status": Task.Status.IN_PROGRESS,
                "due_date": "2026-07-01",
                "days_to_before_trip": "",
                "notes": "Coordinate directly with the hotel.",
            },
        )

        task = Task.objects.get(name="Custom airport handoff")
        self.assertRedirects(response, self.trip.get_absolute_url())
        self.assertIsNone(task.source_template)
        self.assertEqual(task.notes, "Coordinate directly with the hotel.")


class TripDetailTaskManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="tripdetail@example.com",
            password="password",
            is_staff=True,
        )
        self.user.user_permissions.add(
            *Permission.objects.filter(
                codename__in=["view_trip", "change_task", "add_task"]
            )
        )
        self.employee = Employee.objects.create(user=self.user)
        staff_role, _ = Group.objects.get_or_create(name="Staff")
        self.employee.roles.add(staff_role)
        self.second_user = get_user_model().objects.create_user(
            email="assignee@example.com",
            password="password",
        )
        self.second_employee = Employee.objects.create(user=self.second_user)
        self.second_employee.roles.add(staff_role)
        self.status = TripStatus.objects.create(name="Planning")
        self.trip = Trip.objects.create(
            name="Peru 2026",
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            trip_manager=self.employee,
            status=self.status,
        )
        self.first_task = Task.objects.create(
            name="First task",
            trip=self.trip,
            assigned_to=self.employee,
            status=Task.Status.NOT_STARTED,
            due_date=timezone.localdate(),
        )
        self.second_task = Task.objects.create(
            name="Second task",
            trip=self.trip,
            assigned_to=self.employee,
            status=Task.Status.NOT_STARTED,
            due_date=timezone.localdate() + timedelta(days=3),
        )

    def test_trip_detail_shows_inline_task_management_controls(self):
        self.client.force_login(self.user)
        host_role, _ = Group.objects.get_or_create(name="Host")
        host_user = get_user_model().objects.create_user(email="triphost@example.com")
        host_employee = Employee.objects.create(user=host_user)
        host_employee.roles.add(host_role)
        self.trip.trip_leader = host_employee
        self.trip.save()

        response = self.client.get(reverse("trip_detail", args=[self.trip.pk]))

        self.assertContains(response, "Add all tasks")
        self.assertContains(response, "Full edit")
        self.assertContains(response, 'name="trip_manager"')
        self.assertContains(response, 'name="trip_leader"')
        self.assertContains(response, 'name="status"')
        self.assertContains(response, 'name="notes"')
        self.assertContains(
            response,
            reverse("trip_task_status_update", args=[self.trip.pk, self.first_task.pk]),
        )
        self.assertContains(response, 'name="assigned_to"')
        self.assertContains(response, 'name="due_date"')
        self.assertContains(response, "Today")
        self.assertContains(response, "In 3 days")
        self.assertNotContains(response, "Days before trip")
        self.assertNotContains(response, "Created by")

    def test_trip_detail_can_update_single_task_fields(self):
        self.client.force_login(self.user)
        self.first_task.days_to_before_trip = -30
        self.first_task.save()

        response = self.client.post(
            reverse("trip_task_status_update", args=[self.trip.pk, self.first_task.pk]),
            {
                "assigned_to": self.second_employee.pk,
                "status": Task.Status.DONE,
                "due_date": "2026-07-20",
            },
        )

        self.assertRedirects(response, self.trip.get_absolute_url())
        self.first_task.refresh_from_db()
        self.assertEqual(self.first_task.assigned_to, self.second_employee)
        self.assertEqual(self.first_task.status, Task.Status.DONE)
        self.assertEqual(self.first_task.due_date, date(2026, 7, 20))
        self.assertIsNone(self.first_task.days_to_before_trip)

    def test_task_list_quick_update_can_return_json_for_inline_save(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_quick_update", args=[self.first_task.pk]),
            {
                "assigned_to": self.second_employee.pk,
                "status": Task.Status.IN_PROGRESS,
                "due_date": "2026-07-20",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task"]["status"], Task.Status.IN_PROGRESS)
        self.assertEqual(response.json()["task"]["status_label"], "In Progress")
        self.assertEqual(response.json()["task"]["assigned_to"], str(self.second_employee))
        self.assertEqual(response.json()["task"]["due_date"], "2026-07-20")
        self.first_task.refresh_from_db()
        self.assertEqual(self.first_task.assigned_to, self.second_employee)
        self.assertEqual(self.first_task.status, Task.Status.IN_PROGRESS)

    def test_trip_detail_can_bulk_update_task_statuses(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("trip_bulk_task_status_update", args=[self.trip.pk]),
            {
                "status": Task.Status.IN_PROGRESS,
                "task_ids": [str(self.first_task.pk), str(self.second_task.pk)],
            },
        )

        self.assertRedirects(response, self.trip.get_absolute_url())
        self.first_task.refresh_from_db()
        self.second_task.refresh_from_db()
        self.assertEqual(self.first_task.status, Task.Status.IN_PROGRESS)
        self.assertEqual(self.second_task.status, Task.Status.IN_PROGRESS)


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
        self.pack = TaskTemplatePack.objects.create(
            name="Standard Pack",
            sort_order=1,
        )
        self.pack.task_templates.add(self.first_template, self.second_template)

    def _permissions(self, *codenames):
        from django.contrib.auth.models import Permission

        return Permission.objects.filter(codename__in=codenames)

    def test_task_template_list_has_delete_and_drag_controls(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_template_list"))

        self.assertContains(response, "Task Template Packs")
        self.assertContains(response, self.pack.name)
        self.assertContains(response, reverse("task_template_pack_create"))
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

    def test_staff_can_delete_task_template_pack(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_template_pack_delete", args=[self.pack.pk])
        )

        self.assertRedirects(response, reverse("task_template_list"))
        self.assertFalse(TaskTemplatePack.objects.filter(pk=self.pack.pk).exists())


class SeedLegitDefaultsTests(TestCase):
    def test_seed_creates_expected_default_roles(self):
        call_command("seed_legit_defaults", verbosity=0)

        self.assertTrue(Group.objects.filter(name="Administrator").exists())
        self.assertTrue(Group.objects.filter(name="Staff").exists())
        self.assertTrue(Group.objects.filter(name="Host").exists())
        self.assertFalse(Group.objects.filter(name="Operations Manager").exists())
        self.assertFalse(Group.objects.filter(name="Trip Manager").exists())

    def test_seed_does_not_create_default_task_templates_or_packs(self):
        call_command("seed_legit_defaults", verbosity=0)

        self.assertFalse(TaskTemplate.objects.exists())
        self.assertFalse(TaskTemplatePack.objects.exists())

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


class TripAdminImportTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            email="admin@example.com",
            password="password",
        )
        self.staff_role, _ = Group.objects.get_or_create(name="Staff")
        self.host_role, _ = Group.objects.get_or_create(name="Host")
        self.manager_user = get_user_model().objects.create_user(email="manager@example.com")
        self.manager_employee = Employee.objects.create(user=self.manager_user)
        self.manager_employee.roles.add(self.staff_role)
        self.host_user = get_user_model().objects.create_user(email="host@example.com")
        self.host_employee = Employee.objects.create(user=self.host_user)
        self.host_employee.roles.add(self.host_role)
        self.status = TripStatus.objects.create(name="Planning", is_active=True)

    def test_trip_admin_changelist_shows_import_csv_link(self):
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("admin:trips_trip_changelist"))

        self.assertContains(response, reverse("admin:trips_trip_import_csv"))
        self.assertContains(response, "Import CSV")

    def test_admin_can_import_trips_from_csv(self):
        self.client.force_login(self.admin_user)

        csv_content = (
            "name,start_date,end_date,trip_manager_email,status,trip_leader_email,notes\n"
            "Italy Dolomites Adventure,2026-06-12,2026-06-19,manager@example.com,Planning,host@example.com,Imported note\n"
        )
        upload = SimpleUploadedFile(
            "trips.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("admin:trips_trip_import_csv"),
            {"csv_file": upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        trip = Trip.objects.get(name="Italy Dolomites Adventure")
        self.assertEqual(trip.trip_manager, self.manager_employee)
        self.assertEqual(trip.trip_leader, self.host_employee)
        self.assertEqual(trip.status, self.status)
        self.assertEqual(trip.notes, "Imported note")
