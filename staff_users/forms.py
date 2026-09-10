from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from trips.models import Employee

from .models import User


class EmailUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email",)


class EmailUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class StaffUserBaseForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        help_text="These roles also sync to the linked user's Django groups.",
    )

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
        ]
        labels = {
            "is_staff": "Admin access",
        }
        help_texts = {
            "is_staff": "Allows this user to access the Django admin area.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["roles"].queryset = Group.objects.order_by("name")
        if self.instance.pk and hasattr(self.instance, "employee_profile"):
            self.fields["roles"].initial = self.instance.employee_profile.roles.all()

    def save_roles(self, user):
        employee, _ = Employee.objects.get_or_create(user=user)
        employee.roles.set(self.cleaned_data["roles"])
        return employee

    def validate_new_password(self, password, field_name="password1"):
        if not password:
            return
        candidate = self.instance
        for attribute in ("email", "first_name", "last_name"):
            if attribute in self.cleaned_data:
                setattr(candidate, attribute, self.cleaned_data[attribute])
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            self.add_error(field_name, exc)


class StaffUserCreateForm(StaffUserBaseForm):
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta(StaffUserBaseForm.Meta):
        fields = StaffUserBaseForm.Meta.fields

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The two password fields didn't match.")
        elif password1:
            self.validate_new_password(password1)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            self.save_roles(user)
        return user


class StaffUserUpdateForm(StaffUserBaseForm):
    password1 = forms.CharField(
        label="New password",
        strip=False,
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Leave blank to keep the current password.",
    )
    password2 = forms.CharField(
        label="Confirm new password",
        strip=False,
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta(StaffUserBaseForm.Meta):
        fields = StaffUserBaseForm.Meta.fields

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "The two password fields didn't match.")
            elif password1:
                self.validate_new_password(password1)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        if commit:
            user.save()
            self.save_roles(user)
        return user
