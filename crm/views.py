import csv
import io
import mimetypes
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.dateparse import parse_date
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

from .forms import CustomerCsvImportForm, CustomerDocumentForm, CustomerForm, CustomerTripHistoryForm
from .models import Customer, CustomerDocument, CustomerTripHistory


MONEY_FIELD = DecimalField(max_digits=10, decimal_places=2)


def trip_history_annotations():
    return {
        "trip_count": Count("trip_history", distinct=True),
        "total_money_spent": Coalesce(
            Sum("trip_history__money_spent"),
            Value(Decimal("0.00")),
            output_field=MONEY_FIELD,
        ),
    }


class FormTitleMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        action = "Edit" if self.object else "Create"
        context["form_title"] = f"{action} Customer"
        return context


class CustomerListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Customer
    template_name = "crm/customer_list.html"
    context_object_name = "customers"
    permission_required = "crm.view_customer"
    paginate_by = 50

    def get_queryset(self):
        queryset = (
            Customer.objects.prefetch_related("documents")
            .annotate(**trip_history_annotations())
            .order_by(
                "last_name",
                "first_name",
                "id",
            )
        )
        if search := self.request.GET.get("q"):
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone_number__icontains=search)
                | Q(city__icontains=search)
                | Q(state__icontains=search)
                | Q(postal__icontains=search)
                | Q(passport_number__icontains=search)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filters"] = {"q": self.request.GET.get("q", "")}
        context["filters_active"] = bool(context["filters"]["q"])
        context["customer_count"] = Customer.objects.count()
        context["document_count"] = CustomerDocument.objects.count()
        context["trip_history_count"] = CustomerTripHistory.objects.count()
        context["current_querystring"] = self.request.GET.urlencode()
        return context


class CustomerDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Customer
    template_name = "crm/customer_detail.html"
    context_object_name = "customer"
    permission_required = "crm.view_customer"

    def get_queryset(self):
        return Customer.objects.prefetch_related("documents__document_type", "trip_history").annotate(
            **trip_history_annotations()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["document_form"] = CustomerDocumentForm()
        context["trip_history_form"] = CustomerTripHistoryForm()
        return context


class CustomerCreateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "crm/customer_form.html"
    permission_required = "crm.add_customer"


class CustomerCsvImportView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    form_class = CustomerCsvImportForm
    template_name = "crm/customer_import.html"
    permission_required = "crm.add_customer"
    success_url = reverse_lazy("crm_customer_list")

    column_aliases = {
        "first_name": "first_name",
        "firstname": "first_name",
        "first": "first_name",
        "last_name": "last_name",
        "lastname": "last_name",
        "last": "last_name",
        "email": "email",
        "phone_number": "phone_number",
        "phone": "phone_number",
        "address": "address",
        "city": "city",
        "postal": "postal",
        "postal_code": "postal",
        "zip": "postal",
        "zip_code": "postal",
        "state": "state",
        "passport_number": "passport_number",
        "passport": "passport_number",
        "passport_expiration_date": "passport_expiration_date",
        "passport_expiration": "passport_expiration_date",
        "passport_expiry": "passport_expiration_date",
        "notes": "notes",
    }
    customer_fields = [
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "address",
        "city",
        "postal",
        "state",
        "passport_number",
        "passport_expiration_date",
        "notes",
    ]
    required_fields = {"first_name", "last_name", "email"}

    def form_valid(self, form):
        try:
            imported_count, updated_count = self.import_customers(form.cleaned_data["csv_file"])
        except ValidationError as exc:
            for message in exc.messages:
                messages.error(self.request, message)
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"Imported {imported_count} customers and updated {updated_count} existing customers.",
        )
        return super().form_valid(form)

    def import_customers(self, csv_file):
        try:
            decoded = csv_file.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError("Upload a UTF-8 encoded CSV file.") from exc

        reader = csv.DictReader(io.StringIO(decoded))
        if not reader.fieldnames:
            raise ValidationError("The uploaded CSV is empty.")

        field_map = self.build_field_map(reader.fieldnames)
        missing_columns = self.required_fields - set(field_map.values())
        if missing_columns:
            labels = ", ".join(sorted(missing_columns))
            raise ValidationError(f"Missing required columns: {labels}.")

        rows_to_import = self.build_customer_rows(reader, field_map)
        imported_count = 0
        updated_count = 0
        for customer_data in rows_to_import:
            existing_customer = Customer.objects.filter(email__iexact=customer_data["email"]).first()
            if existing_customer:
                for field, value in customer_data.items():
                    setattr(existing_customer, field, value)
                existing_customer.save()
                updated_count += 1
            else:
                Customer.objects.create(**customer_data)
                imported_count += 1

        return imported_count, updated_count

    def build_field_map(self, fieldnames):
        field_map = {}
        for fieldname in fieldnames:
            normalized = self.normalize_column(fieldname)
            if mapped_field := self.column_aliases.get(normalized):
                field_map[fieldname] = mapped_field
        return field_map

    def build_customer_rows(self, reader, field_map):
        rows = []
        errors = []
        for index, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue

            row_errors = []
            customer_data = {field: "" for field in self.customer_fields}
            for source_column, target_field in field_map.items():
                customer_data[target_field] = (row.get(source_column) or "").strip()

            for required_field in self.required_fields:
                if not customer_data[required_field]:
                    row_errors.append(f"Row {index}: {required_field} is required.")

            expiration_value = customer_data["passport_expiration_date"]
            if expiration_value:
                expiration_date = parse_date(expiration_value)
                if expiration_date is None:
                    row_errors.append(
                        f"Row {index}: passport_expiration_date must be in YYYY-MM-DD format."
                    )
                customer_data["passport_expiration_date"] = expiration_date
            else:
                customer_data["passport_expiration_date"] = None

            if row_errors:
                errors.extend(row_errors)
                continue

            rows.append(customer_data)

        if errors:
            raise ValidationError(errors)
        return rows

    @staticmethod
    def normalize_column(column):
        return (column or "").strip().lower().replace(" ", "_").replace("-", "_")


class CustomerUpdateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "crm/customer_form.html"
    permission_required = "crm.change_customer"


class CustomerDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Customer
    template_name = "crm/customer_confirm_delete.html"
    permission_required = "crm.delete_customer"
    success_url = reverse_lazy("crm_customer_list")

    def form_valid(self, form):
        messages.success(self.request, f"Deleted {self.object.full_name}.")
        return super().form_valid(form)


class CustomerDocumentCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "crm.add_customerdocument"

    def post(self, request, customer_pk):
        customer = get_object_or_404(Customer, pk=customer_pk)
        form = CustomerDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.customer = customer
            document.save()
            messages.success(request, f"Attached {document.display_name}.")
        else:
            messages.error(request, "Please choose a PDF or image to attach.")
        return redirect(customer)


class CustomerDocumentDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "crm.delete_customerdocument"

    def post(self, request, customer_pk, pk):
        customer = get_object_or_404(Customer, pk=customer_pk)
        document = get_object_or_404(CustomerDocument, pk=pk, customer=customer)
        display_name = document.display_name
        document.delete()
        messages.success(request, f"Removed {display_name}.")
        return redirect(customer)


class CustomerDocumentServeView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "crm.view_customer"

    def get(self, request, customer_pk, pk):
        customer = get_object_or_404(Customer, pk=customer_pk)
        document = get_object_or_404(CustomerDocument, pk=pk, customer=customer)
        content_type, _ = mimetypes.guess_type(document.file.name)
        response = FileResponse(
            document.file.open("rb"),
            as_attachment=False,
            filename=document.display_name,
            content_type=content_type or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class CustomerTripHistoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "crm.add_customertriphistory"

    def post(self, request, customer_pk):
        customer = get_object_or_404(Customer, pk=customer_pk)
        form = CustomerTripHistoryForm(request.POST)
        if form.is_valid():
            trip_history = form.save(commit=False)
            trip_history.customer = customer
            trip_history.save()
            messages.success(request, f"Added trip history for {trip_history.trip_name}.")
        else:
            messages.error(request, "Please enter a valid trip name, dates, and amount spent.")
        return redirect(customer)


class CustomerTripHistoryDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "crm.delete_customertriphistory"

    def post(self, request, customer_pk, pk):
        customer = get_object_or_404(Customer, pk=customer_pk)
        trip_history = get_object_or_404(CustomerTripHistory, pk=pk, customer=customer)
        trip_name = trip_history.trip_name
        trip_history.delete()
        messages.success(request, f"Removed trip history for {trip_name}.")
        return redirect(customer)
