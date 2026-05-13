from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Employee(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    roles = models.ManyToManyField(
        Group,
        blank=True,
        related_name="employees",
        help_text="Employee permission roles. These sync to the linked user's groups.",
    )

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return self.full_name or self.user.get_username()

    @property
    def first_name(self):
        return self.user.first_name

    @property
    def last_name(self):
        return self.user.last_name

    @property
    def email(self):
        return self.user.email

    @property
    def full_name(self):
        return self.user.get_full_name()

    @property
    def role_names(self):
        return ", ".join(self.roles.values_list("name", flat=True)) or "No roles"

    def sync_user_groups(self):
        self.user.groups.set(self.roles.all())


class TripStatus(TimeStampedModel):
    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "trip statuses"

    def __str__(self):
        return self.name


class Trip(TimeStampedModel):
    name = models.CharField(max_length=180)
    start_date = models.DateField()
    end_date = models.DateField()
    trip_manager = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="managed_trips",
    )
    created_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_trips",
    )
    status = models.ForeignKey(
        TripStatus,
        on_delete=models.PROTECT,
        related_name="trips",
    )
    notes = models.TextField(
        blank=True,
        help_text="Stores rich text/HTML produced by the staff editor.",
    )
    trip_leader = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hosted_trips",
        help_text="Host employee going on the trip.",
    )

    class Meta:
        ordering = ["start_date"]
        permissions = [
            ("manage_trip_statuses", "Can manage trip statuses"),
            ("view_trip_dashboard", "Can view the trip dashboard"),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"

    def get_absolute_url(self):
        return reverse("trip_detail", kwargs={"pk": self.pk})

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before start date."})

    @property
    def open_tasks_count(self):
        return self.tasks.exclude(status=Task.Status.DONE).count()

    def apply_task_templates(self, assigned_to=None, status=None, templates=None):
        template_queryset = templates or TaskTemplate.objects.filter(is_active=True)
        tasks = [
            template.build_task(self)
            for template in template_queryset
            if not self.tasks.filter(source_template=template).exists()
        ]
        for task in tasks:
            if assigned_to:
                task.assigned_to = assigned_to
            if status:
                task.status = status

        if tasks:
            Task.objects.bulk_create(tasks)
        return len(tasks)


class TaskTemplate(TimeStampedModel):
    name = models.CharField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    default_notes = models.TextField(blank=True)
    days_to_before_trip = models.IntegerField(
        null=True,
        blank=True,
        help_text="Days from trip start. Use negative numbers before the trip and positive numbers after.",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def day_offset_display(self):
        if self.days_to_before_trip is None:
            return "No default"
        if self.days_to_before_trip == 0:
            return "Trip start"
        if self.days_to_before_trip < 0:
            return f"{abs(self.days_to_before_trip)} days before"
        return f"{self.days_to_before_trip} days after"

    def build_task(self, trip):
        due_date = None
        if self.days_to_before_trip is not None:
            due_date = trip.start_date + timedelta(days=self.days_to_before_trip)

        return Task(
            name=self.name,
            trip=trip,
            notes=self.default_notes,
            days_to_before_trip=self.days_to_before_trip,
            due_date=due_date,
            source_template=self,
        )


class TaskTemplatePack(TimeStampedModel):
    name = models.CharField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    task_templates = models.ManyToManyField(
        TaskTemplate,
        blank=True,
        related_name="packs",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def active_template_count(self):
        return self.task_templates.filter(is_active=True).count()


class Task(TimeStampedModel):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not Started"
        IN_PROGRESS = "in_progress", "In Progress"
        DONE = "done", "Done"

    name = models.CharField(max_length=180)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="tasks")
    source_template = models.ForeignKey(
        TaskTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_tasks",
    )
    due_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    notes = models.TextField(blank=True)
    days_to_before_trip = models.IntegerField(
        null=True,
        blank=True,
        help_text="Days from trip start. Use negative numbers before the trip and positive numbers after.",
    )

    class Meta:
        ordering = ["due_date", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "source_template"],
                condition=Q(source_template__isnull=False),
                name="unique_task_template_per_trip",
            )
        ]
        permissions = [
            ("assign_task", "Can assign trip tasks"),
            ("complete_task", "Can complete trip tasks"),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.days_to_before_trip is not None:
            self.due_date = self.trip.start_date + self._days_delta()
        super().save(*args, **kwargs)

    def _days_delta(self):
        return timedelta(days=self.days_to_before_trip)

    @property
    def due_in_days(self):
        if not self.due_date:
            return None
        return (self.due_date - timezone.localdate()).days

    @property
    def due_in_display(self):
        if self.status == self.Status.DONE:
            return "Done"
        due_in_days = self.due_in_days
        if due_in_days is None:
            return "-"
        if due_in_days == 0:
            return "Today"
        if due_in_days < 0:
            return f"Overdue by {abs(due_in_days)} days"
        return f"In {due_in_days} days"
