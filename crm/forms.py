from django import forms

from .models import Customer, CustomerDocument, CustomerDocumentType, CustomerTripHistory


class DateInput(forms.DateInput):
    input_type = "date"


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "address",
            "city",
            "state",
            "postal",
            "passport_number",
            "passport_expiration_date",
            "notes",
        ]
        widgets = {
            "passport_expiration_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 6}),
        }


class CustomerCsvImportForm(forms.Form):
    csv_file = forms.FileField(
        help_text=(
            "Required columns: First_Name, Last_Name, Email. Optional columns: "
            "Phone Number, Address, City, Postal, State, Passport Number, "
            "Passport Expiration date, Notes."
        )
    )


class CustomerDocumentForm(forms.ModelForm):
    document_type = forms.ModelChoiceField(
        queryset=CustomerDocumentType.objects.filter(is_active=True),
        empty_label="Select a document type",
        required=False,
    )

    class Meta:
        model = CustomerDocument
        fields = ["document_type", "title", "file", "notes"]
        help_texts = {
            "file": "Accepted file types: PDF, JPG, PNG, GIF, or WebP.",
        }


class CustomerTripHistoryForm(forms.ModelForm):
    class Meta:
        model = CustomerTripHistory
        fields = ["trip_name", "trip_start_date", "trip_end_date", "money_spent"]
        widgets = {
            "trip_start_date": DateInput(),
            "trip_end_date": DateInput(),
        }
