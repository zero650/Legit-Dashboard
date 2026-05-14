from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from trips.models import Employee

from .forms import StaffUserCreateForm, StaffUserUpdateForm
from .models import User


class StaffFormTitleMixin:
    page_kicker = "Staff system"
    page_intro = (
        "Create employees, manage login access, and keep staff roles aligned with the rest of the dashboard."
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        action = "Edit" if self.object else "Create"
        context["form_title"] = f"{action} Staff Member"
        context["page_kicker"] = self.page_kicker
        context["page_intro"] = self.page_intro
        return context


class StaffListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = User
    template_name = "staff_users/staff_list.html"
    context_object_name = "staff_members"
    permission_required = "staff_users.view_user"
    paginate_by = 50

    def get_queryset(self):
        queryset = (
            User.objects.select_related("employee_profile")
            .prefetch_related("employee_profile__roles")
            .annotate(
                managed_trip_count=Count("employee_profile__managed_trips", distinct=True),
                assigned_task_count=Count(
                    "employee_profile__tasks",
                    filter=~Q(employee_profile__tasks__status="done"),
                    distinct=True,
                ),
            )
            .order_by("last_name", "first_name", "email")
        )

        if search := self.request.GET.get("q"):
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(employee_profile__roles__name__icontains=search)
            ).distinct()

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for staff_member in context["staff_members"]:
            employee_profile = getattr(staff_member, "employee_profile", None)
            staff_member.role_list = list(employee_profile.roles.all()) if employee_profile else []
        context["filters"] = {"q": self.request.GET.get("q", "")}
        context["filters_active"] = bool(context["filters"]["q"])
        context["staff_count"] = Employee.objects.count()
        context["active_trip_manager_count"] = Employee.objects.filter(
            roles__name__in=["Administrator", "Staff"],
        ).distinct().count()
        context["host_count"] = Employee.objects.filter(roles__name="Host").distinct().count()
        return context


class StaffCreateView(StaffFormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = User
    form_class = StaffUserCreateForm
    template_name = "staff_users/staff_form.html"
    permission_required = "staff_users.add_user"
    success_url = reverse_lazy("staff_list")

    def form_valid(self, form):
        messages.success(self.request, f"Created {form.instance.get_full_name() or form.instance.email}.")
        return super().form_valid(form)


class StaffUpdateView(StaffFormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = User
    form_class = StaffUserUpdateForm
    template_name = "staff_users/staff_form.html"
    permission_required = "staff_users.change_user"
    success_url = reverse_lazy("staff_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Updated {self.object.get_full_name() or self.object.email}.")
        return response
