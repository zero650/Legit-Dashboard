from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import connection

from trips.models import TaskTemplate, TripStatus


DEFAULT_STATUSES = [
    "Completed",
    "Closed",
    "Planning",
    "On Sale",
]

DEFAULT_TASK_TEMPLATES = [
    ("Itinerary/Pricing Confirmed", -365, ""),
    ("Trip Page for Website", -365, ""),
    ("Trip Frienzy Creation", -180, "Use website and/or itinerary from DMC to create Frienzy"),
    ("Guests Paid in Full?", -125, ""),
    ("Pre-Trip Q&A", -120, ""),
    ("Submit Rooming List", -60, ""),
    ("Pre/Post Nights Added", -60, ""),
    ("Invoice for Extras", -30, ""),
    ("Mail Bracelets", -30, ""),
    ("Transfer Schedule", -30, ""),
    ("Pre-Trip Call w/ Host", -30, ""),
    ("Upload Guest Addresses to TouchNote", -1, ""),
    ("Request Reviews", 1, ""),
    ("Mail TouchNotes", 1, ""),
    (
        "Thank Local Partner",
        10,
        "Send a few photos from the trip with happy smiling faces and thank the local partner.",
    ),
]

LEGACY_TASK_TEMPLATE_NAMES = [
    "Confirm trip leader agreement",
    "Finalize itinerary",
    "Confirm hotel room block",
    "Confirm group transportation",
    "Review vendor payment schedule",
    "Publish traveler information packet",
    "Collect traveler passport details",
    "Confirm activity reservations",
    "Send final payment reminders",
    "Collect rooming list",
    "Confirm dietary restrictions",
    "Send pre-trip email",
    "Review emergency contact list",
    "Confirm final headcount with vendors",
    "Send departure reminders",
]

GROUP_PERMISSIONS = {
    "Administrator": [
        "add_employee",
        "change_employee",
        "delete_employee",
        "view_employee",
        "add_user",
        "change_user",
        "delete_user",
        "view_user",
        "add_role",
        "change_role",
        "delete_role",
        "view_role",
        "change_rolepermission",
        "view_rolepermission",
        "add_trip",
        "change_trip",
        "delete_trip",
        "view_trip",
        "manage_trip_statuses",
        "view_trip_dashboard",
        "add_tripstatus",
        "change_tripstatus",
        "view_tripstatus",
        "add_task",
        "change_task",
        "delete_task",
        "view_task",
        "add_tasktemplate",
        "change_tasktemplate",
        "delete_tasktemplate",
        "view_tasktemplate",
        "assign_task",
        "complete_task",
    ],
    "Staff": [
        "view_trip",
        "view_trip_dashboard",
        "add_task",
        "change_task",
        "view_task",
        "view_tasktemplate",
        "complete_task",
    ],
    "Host": [
        "view_trip",
        "view_task",
    ],
}

LEGACY_ROLE_RENAMES = {
    "Operations Manager": "Administrator",
    "Trip Manager": "Staff",
}


class Command(BaseCommand):
    help = "Create default trip statuses, task templates, and staff role groups."

    def handle(self, *args, **options):
        for index, status_name in enumerate(DEFAULT_STATUSES, start=1):
            TripStatus.objects.update_or_create(
                name=status_name,
                defaults={
                    "sort_order": index,
                    "is_active": True,
                },
            )

        TripStatus.objects.exclude(name__in=DEFAULT_STATUSES).update(is_active=False)

        for index, (name, day_offset, notes) in enumerate(DEFAULT_TASK_TEMPLATES, start=1):
            TaskTemplate.objects.update_or_create(
                name=name,
                defaults={
                    "days_to_before_trip": day_offset,
                    "default_notes": notes,
                    "sort_order": index,
                    "is_active": True,
                },
            )

        TaskTemplate.objects.filter(
            name__in=LEGACY_TASK_TEMPLATE_NAMES,
        ).exclude(
            name__in=[name for name, _, _ in DEFAULT_TASK_TEMPLATES],
        ).update(is_active=False)

        for old_name, new_name in LEGACY_ROLE_RENAMES.items():
            old_group = Group.objects.filter(name=old_name).first()
            if not old_group:
                continue

            new_group, _ = Group.objects.get_or_create(name=new_name)
            new_group.permissions.add(*old_group.permissions.all())
            table_names = connection.introspection.table_names()
            if "staff_users_user" in table_names:
                for user in old_group.user_set.all():
                    user.groups.add(new_group)
            if "trips_employee_roles" in table_names:
                for employee in old_group.employees.all():
                    employee.roles.add(new_group)
            old_group.delete()

        for group_name, codenames in GROUP_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            permissions = Permission.objects.filter(codename__in=codenames)
            group.permissions.set(permissions)

        self.stdout.write(self.style.SUCCESS("Seeded Legit Dashboard defaults."))
