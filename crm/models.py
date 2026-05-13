from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse


class Customer(models.Model):
    first_name = models.CharField("First name", max_length=80)
    last_name = models.CharField("Last name", max_length=80)
    email = models.EmailField()
    phone_number = models.CharField("Phone number", max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=80, blank=True)
    postal = models.CharField("Postal code", max_length=20, blank=True)
    passport_number = models.CharField(max_length=80, blank=True)
    passport_expiration_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["last_name", "first_name", "id"]
        permissions = [
            ("view_crm", "Can view CRM"),
        ]

    def __str__(self):
        return self.full_name

    def get_absolute_url(self):
        return reverse("crm_customer_detail", kwargs={"pk": self.pk})

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def location(self):
        parts = [self.city, self.state, self.postal]
        return ", ".join(part for part in parts if part)


class CustomerDocument(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=160, blank=True)
    file = models.FileField(
        upload_to="crm/customer-documents/%Y/%m/",
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "jpg", "jpeg", "png", "gif", "webp"],
            )
        ],
    )
    notes = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "id"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.title or self.file.name.rsplit("/", 1)[-1]

    @property
    def is_image(self):
        return self.file.name.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))


class CustomerTripHistory(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="trip_history",
    )
    trip_name = models.CharField(max_length=180)
    trip_start_date = models.DateField()
    trip_end_date = models.DateField()
    money_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-trip_start_date", "trip_name", "id"]
        verbose_name_plural = "customer trip history"

    def __str__(self):
        return f"{self.customer.full_name} - {self.trip_name}"


@receiver(post_delete, sender=CustomerDocument)
def delete_customer_document_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
