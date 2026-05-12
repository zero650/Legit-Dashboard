from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import Employee


@receiver(m2m_changed, sender=Employee.roles.through)
def sync_employee_roles_to_user_groups(sender, instance, action, **kwargs):
    if action in {"post_add", "post_remove", "post_clear"}:
        instance.sync_user_groups()
