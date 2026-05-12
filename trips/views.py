from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import JsonResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from .forms import TaskCreateForm, TaskForm, TaskTemplateForm, TripForm
from .models import Task, TaskTemplate, Trip


class FormTitleMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        action = "Edit" if self.object else "Create"
        context["form_title"] = f"{action} {self.model._meta.verbose_name.title()}"
        return context


class TripDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "trips/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["upcoming_trips"] = (
            Trip.objects.select_related("trip_manager", "trip_manager__user", "status")
            .annotate(open_tasks=Count("tasks", filter=~Q(tasks__status=Task.Status.DONE)))
            .order_by("start_date")[:8]
        )
        context["open_tasks"] = (
            Task.objects.select_related("trip", "assigned_to", "assigned_to__user")
            .exclude(status=Task.Status.DONE)
            .order_by("due_date", "created_at")[:12]
        )
        context["trip_count"] = Trip.objects.count()
        context["open_task_count"] = Task.objects.exclude(status=Task.Status.DONE).count()
        context["task_template_count"] = TaskTemplate.objects.filter(is_active=True).count()
        return context


class TripListView(LoginRequiredMixin, ListView):
    model = Trip
    template_name = "trips/trip_list.html"
    context_object_name = "trips"
    paginate_by = 25

    def get_queryset(self):
        return Trip.objects.select_related("trip_manager", "trip_manager__user", "status")


class TripDetailView(LoginRequiredMixin, DetailView):
    model = Trip
    template_name = "trips/trip_detail.html"
    context_object_name = "trip"

    def get_queryset(self):
        return Trip.objects.select_related(
            "trip_manager",
            "trip_manager__user",
            "status",
        ).prefetch_related("tasks", "tasks__assigned_to", "tasks__assigned_to__user")


class TripCreateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Trip
    form_class = TripForm
    template_name = "trips/form.html"
    permission_required = "trips.add_trip"

    def form_valid(self, form):
        if hasattr(self.request.user, "employee_profile"):
            form.instance.created_by = self.request.user.employee_profile
        return super().form_valid(form)


class TripUpdateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Trip
    form_class = TripForm
    template_name = "trips/form.html"
    permission_required = "trips.change_trip"


class ApplyTaskTemplatesView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "trips.add_task"

    def post(self, request, pk):
        trip = get_object_or_404(Trip, pk=pk)
        assignee = trip.created_by or trip.trip_manager
        created_count = trip.apply_task_templates(
            assigned_to=assignee,
            status=Task.Status.IN_PROGRESS,
        )
        if created_count:
            messages.success(request, f"Added {created_count} tasks and assigned them to {assignee}.")
        else:
            messages.info(request, "No new tasks were added. Active templates were already applied.")
        return redirect(trip)


class TaskCreateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Task
    form_class = TaskCreateForm
    template_name = "trips/form.html"
    permission_required = "trips.add_task"

    def get_initial(self):
        initial = super().get_initial()
        if trip_id := self.request.GET.get("trip"):
            initial["trip"] = trip_id
        return initial

    def get_success_url(self):
        return self.object.trip.get_absolute_url()


class TaskTemplateListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = TaskTemplate
    template_name = "trips/task_template_list.html"
    context_object_name = "task_templates"
    permission_required = "trips.view_tasktemplate"


class TaskTemplateDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "trips.delete_tasktemplate"

    def post(self, request, pk):
        task_template = get_object_or_404(TaskTemplate, pk=pk)
        task_template.delete()
        messages.success(request, "Task template deleted.")
        return redirect("task_template_list")


class TaskTemplateReorderView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "trips.change_tasktemplate"

    def post(self, request):
        ordered_ids = [
            int(template_id)
            for template_id in request.POST.getlist("template_ids[]")
            if template_id.isdigit()
        ]
        templates = {
            template.pk: template
            for template in TaskTemplate.objects.filter(pk__in=ordered_ids)
        }

        for index, template_id in enumerate(ordered_ids, start=1):
            if template := templates.get(template_id):
                template.sort_order = index

        if templates:
            TaskTemplate.objects.bulk_update(templates.values(), ["sort_order"])

        return JsonResponse({"updated": len(templates)})


class TaskTemplateCreateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = TaskTemplate
    form_class = TaskTemplateForm
    template_name = "trips/form.html"
    permission_required = "trips.add_tasktemplate"
    success_url = reverse_lazy("task_template_list")


class TaskTemplateUpdateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = TaskTemplate
    form_class = TaskTemplateForm
    template_name = "trips/form.html"
    permission_required = "trips.change_tasktemplate"
    success_url = reverse_lazy("task_template_list")


class TaskUpdateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "trips/form.html"
    permission_required = "trips.change_task"

    def get_success_url(self):
        return self.object.trip.get_absolute_url()
