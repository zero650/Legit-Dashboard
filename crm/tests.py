import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from .forms import CustomerDocumentForm
from .models import Customer, CustomerDocument, CustomerDocumentType, CustomerTripHistory


TEMP_MEDIA_ROOT = tempfile.mkdtemp()


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)


class CustomerModelTests(TestCase):
    def test_full_name_and_location_display(self):
        customer = Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
            city="Denver",
            state="CO",
            postal="80202",
        )

        self.assertEqual(customer.full_name, "Avery Stone")
        self.assertEqual(customer.location, "Denver, CO, 80202")


class CustomerDocumentFormTests(TestCase):
    def test_document_type_choices_only_show_active_types(self):
        active_type = CustomerDocumentType.objects.get(name="Passport")
        inactive_type = CustomerDocumentType.objects.create(name="Retired", is_active=False)

        form = CustomerDocumentForm()

        self.assertIn(active_type, form.fields["document_type"].queryset)
        self.assertNotIn(inactive_type, form.fields["document_type"].queryset)

    def test_rejects_unsupported_file_type(self):
        form = CustomerDocumentForm(
            data={"title": "Spreadsheet"},
            files={
                "file": SimpleUploadedFile(
                    "manifest.xlsx",
                    b"fake spreadsheet",
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class CustomerViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="password",
        )
        permissions = Permission.objects.filter(
            codename__in=[
                "view_customer",
                "add_customer",
                "change_customer",
                "add_customerdocument",
                "delete_customerdocument",
                "add_customertriphistory",
                "delete_customertriphistory",
            ]
        )
        self.user.user_permissions.set(permissions)
        self.client.force_login(self.user)

    def test_customer_list_searches_by_email(self):
        Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
        )
        Customer.objects.create(
            first_name="Jordan",
            last_name="Reed",
            email="jordan@example.com",
        )

        response = self.client.get(reverse("crm_customer_list"), {"q": "avery@example.com"})

        self.assertContains(response, "Avery Stone")
        self.assertNotContains(response, "Jordan Reed")

    def test_customer_list_shows_trip_count_and_total_spend(self):
        customer = Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
        )
        CustomerTripHistory.objects.create(
            customer=customer,
            trip_name="Greece",
            trip_start_date="2026-06-01",
            trip_end_date="2026-06-08",
            money_spent="2500.00",
        )
        CustomerTripHistory.objects.create(
            customer=customer,
            trip_name="Italy",
            trip_start_date="2026-09-01",
            trip_end_date="2026-09-08",
            money_spent="3200.50",
        )

        response = self.client.get(reverse("crm_customer_list"))

        self.assertContains(response, "Avery Stone")
        self.assertContains(response, "2")
        self.assertContains(response, "$5700.50")

    def test_can_attach_customer_document(self):
        customer = Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
        )
        document_type = CustomerDocumentType.objects.get(name="Passport")

        response = self.client.post(
            reverse("crm_customer_document_create", kwargs={"customer_pk": customer.pk}),
            {
                "document_type": document_type.pk,
                "title": "Passport",
                "file": SimpleUploadedFile(
                    "passport.pdf",
                    b"%PDF-1.4",
                    content_type="application/pdf",
                ),
            },
        )

        self.assertRedirects(response, customer.get_absolute_url())
        document = CustomerDocument.objects.get(customer=customer)
        self.assertEqual(document.title, "Passport")
        self.assertEqual(document.document_type, document_type)

    def test_customer_detail_lists_document_titles_without_inline_previews(self):
        customer = Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
        )
        document_type = CustomerDocumentType.objects.get(name="Government ID")
        document = CustomerDocument.objects.create(
            customer=customer,
            document_type=document_type,
            title="Driver License",
            file=SimpleUploadedFile("license.jpg", b"fake image", content_type="image/jpeg"),
            notes="Front side",
        )

        response = self.client.get(customer.get_absolute_url())

        self.assertContains(response, "Driver License")
        self.assertContains(response, "Government ID")
        self.assertContains(
            response,
            reverse("crm_customer_document_file", kwargs={"customer_pk": customer.pk, "pk": document.pk}),
        )
        self.assertNotContains(response, "<img")

    def test_customer_document_file_requires_authentication(self):
        customer = Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
        )
        document = CustomerDocument.objects.create(
            customer=customer,
            title="Passport",
            file=SimpleUploadedFile("passport.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )

        self.client.logout()
        response = self.client.get(
            reverse("crm_customer_document_file", kwargs={"customer_pk": customer.pk, "pk": document.pk})
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_customer_document_file_requires_view_permission(self):
        customer = Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
        )
        document = CustomerDocument.objects.create(
            customer=customer,
            title="Passport",
            file=SimpleUploadedFile("passport.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )
        self.user.user_permissions.remove(
            Permission.objects.get(codename="view_customer")
        )

        response = self.client.get(
            reverse("crm_customer_document_file", kwargs={"customer_pk": customer.pk, "pk": document.pk})
        )

        self.assertEqual(response.status_code, 403)

    def test_customer_document_file_streams_for_authorized_user(self):
        customer = Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
        )
        document = CustomerDocument.objects.create(
            customer=customer,
            title="Passport",
            file=SimpleUploadedFile("passport.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )

        response = self.client.get(
            reverse("crm_customer_document_file", kwargs={"customer_pk": customer.pk, "pk": document.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_can_add_customer_trip_history(self):
        customer = Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
        )

        response = self.client.post(
            reverse("crm_customer_trip_history_create", kwargs={"customer_pk": customer.pk}),
            {
                "trip_name": "Iceland Winter",
                "trip_start_date": "2026-02-01",
                "trip_end_date": "2026-02-08",
                "money_spent": "4100.75",
            },
        )

        self.assertRedirects(response, customer.get_absolute_url())
        trip_history = CustomerTripHistory.objects.get(customer=customer)
        self.assertEqual(trip_history.trip_name, "Iceland Winter")
        self.assertEqual(str(trip_history.money_spent), "4100.75")

    def test_can_import_customers_from_csv(self):
        csv_file = SimpleUploadedFile(
            "customers.csv",
            (
                "First_Name,Last_Name,Email,Phone Number,Address,City,Postal,State,"
                "Passport Number,Passport Expiration date,Notes\n"
                "Avery,Stone,avery@example.com,555-1212,123 Main St,Denver,80202,CO,"
                "P12345,2030-01-15,VIP traveler\n"
            ).encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("crm_customer_import"),
            {"csv_file": csv_file},
        )

        self.assertRedirects(response, reverse("crm_customer_list"))
        customer = Customer.objects.get(email="avery@example.com")
        self.assertEqual(customer.first_name, "Avery")
        self.assertEqual(customer.phone_number, "555-1212")
        self.assertEqual(customer.passport_expiration_date.isoformat(), "2030-01-15")

    def test_customer_import_updates_existing_customer_by_email(self):
        customer = Customer.objects.create(
            first_name="Avery",
            last_name="Stone",
            email="avery@example.com",
            city="Denver",
        )
        csv_file = SimpleUploadedFile(
            "customers.csv",
            "First_Name,Last_Name,Email,City\nAvery,Stone,avery@example.com,Boulder\n".encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("crm_customer_import"),
            {"csv_file": csv_file},
        )

        self.assertRedirects(response, reverse("crm_customer_list"))
        customer.refresh_from_db()
        self.assertEqual(customer.city, "Boulder")
        self.assertEqual(Customer.objects.filter(email="avery@example.com").count(), 1)

    def test_customer_import_rejects_missing_required_columns(self):
        csv_file = SimpleUploadedFile(
            "customers.csv",
            "First_Name,Email\nAvery,avery@example.com\n".encode(),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("crm_customer_import"),
            {"csv_file": csv_file},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Customer.objects.filter(email="avery@example.com").exists())
