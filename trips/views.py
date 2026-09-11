from datetime import timedelta

from django import forms
from django.db import transaction
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, ExpressionWrapper, F, IntegerField, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from crm.models import Customer

from .forms import (
    TaskCreateForm,
    TaskForm,
    TaskQuickUpdateForm,
    TaskWorkspaceUpdateForm,
    TaskTemplateForm,
    TaskTemplatePackForm,
    TripForm,
    TripQuickUpdateForm,
)
from .models import Employee, Task, TaskTemplate, TaskTemplatePack, Trip


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
        today = timezone.localdate()
        context["upcoming_trips"] = (
            Trip.objects.select_related("trip_manager", "trip_manager__user", "status")
            .filter(end_date__gte=today)
            .annotate(open_tasks=Count("tasks", filter=~Q(tasks__status=Task.Status.DONE)))
            .order_by("start_date")[:8]
        )
        context["can_view_tasks"] = self.request.user.has_perm("trips.view_task")
        context["open_tasks"] = []
        if context["can_view_tasks"]:
            context["open_tasks"] = (
                Task.objects.select_related("trip", "assigned_to", "assigned_to__user")
                .exclude(status=Task.Status.DONE)
                .order_by("due_date", "created_at")[:12]
            )
        context["trip_count"] = Trip.objects.count()
        context["open_task_count"] = (
            Task.objects.exclude(status=Task.Status.DONE).count()
            if context["can_view_tasks"]
            else None
        )
        context["running_trip_count"] = Trip.objects.exclude(
            status__name__in=["Completed", "Closed"],
        ).filter(
            start_date__lte=today,
            end_date__gte=today,
        ).count()
        context["can_view_crm"] = self.request.user.has_perm("crm.view_customer")
        context["top_customers"] = []
        if context["can_view_crm"]:
            context["top_customers"] = (
                Customer.objects.annotate(
                    trip_count=ExpressionWrapper(
                        Count("trip_history") + F("woocommerce_order_count"),
                        output_field=IntegerField(),
                    )
                )
                .filter(trip_count__gt=0)
                .order_by("-trip_count", "last_name", "first_name")[:5]
            )
        return context


class TripListView(LoginRequiredMixin, ListView):
    model = Trip
    template_name = "trips/trip_list.html"
    context_object_name = "trips"
    paginate_by = 25

    def get_queryset(self):
        queryset = Trip.objects.select_related(
            "trip_manager",
            "trip_manager__user",
            "trip_leader",
            "trip_leader__user",
            "status",
        ).annotate(
            open_tasks=Count("tasks", filter=~Q(tasks__status=Task.Status.DONE))
        ).order_by("start_date", "id")

        if search := self.request.GET.get("q"):
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(trip_manager__user__first_name__icontains=search)
                | Q(trip_manager__user__last_name__icontains=search)
                | Q(trip_manager__user__email__icontains=search)
                | Q(trip_leader__user__first_name__icontains=search)
                | Q(trip_leader__user__last_name__icontains=search)
                | Q(trip_leader__user__email__icontains=search)
            )

        if status := self.request.GET.get("status"):
            queryset = queryset.filter(status_id=status)

        if trip_manager := self.request.GET.get("trip_manager"):
            queryset = queryset.filter(trip_manager_id=trip_manager)

        if trip_leader := self.request.GET.get("trip_leader"):
            queryset = queryset.filter(trip_leader_id=trip_leader)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = {
            "q": self.request.GET.get("q", ""),
            "status": self.request.GET.get("status", ""),
            "trip_manager": self.request.GET.get("trip_manager", ""),
            "trip_leader": self.request.GET.get("trip_leader", ""),
        }
        context["trip_managers"] = Employee.objects.filter(
            roles__name__in=["Administrator", "Staff"],
        ).distinct()
        context["trip_leaders"] = Employee.objects.filter(
            roles__name="Host",
        ).distinct()
        context["trip_statuses"] = TripForm().fields["status"].queryset
        context["filters"] = filters
        context["filters_active"] = any(filters.values())
        context["current_querystring"] = self.request.GET.urlencode()
        return context


class TripQuickUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "trips.change_trip"

    def post(self, request, pk):
        trip = get_object_or_404(Trip, pk=pk)
        wants_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        data = request.POST.copy()
        if "trip_leader" not in data:
            data["trip_leader"] = trip.trip_leader_id or ""
        if "trip_manager" not in data:
            data["trip_manager"] = trip.trip_manager_id
        if "status" not in data:
            data["status"] = trip.status_id
        if "notes" not in data:
            data["notes"] = trip.notes

        form = TripQuickUpdateForm(data, instance=trip)
        if not form.is_valid():
            if wants_json:
                return JsonResponse(
                    {
                        "ok": False,
                        "errors": form.errors.get_json_data(),
                    },
                    status=400,
                )
            messages.error(request, "Please choose a valid leader, manager, or status.")
        else:
            trip = form.save()
            if wants_json:
                leader_label = "No leader"
                if trip.trip_leader:
                    leader_label = trip.trip_leader.full_name or trip.trip_leader.email
                manager_label = trip.trip_manager.full_name or trip.trip_manager.email
                return JsonResponse(
                    {
                        "ok": True,
                        "trip": {
                            "id": trip.pk,
                            "trip_leader": leader_label,
                            "trip_manager": manager_label,
                            "status_id": trip.status_id,
                            "status_label": trip.status.name,
                        },
                    }
                )
            messages.success(request, f"Updated {trip.name}.")
        return redirect(request.POST.get("next") or "trip_list")


def task_view_queries(user):
    today = timezone.localdate()
    unfinished = ~Q(status=Task.Status.DONE)
    return {
        "open": ("Open", unfinished),
        "mine": ("My tasks", unfinished & Q(assigned_to__user=user)),
        "overdue": ("Overdue", unfinished & Q(due_date__lt=today)),
        "today": ("Today", unfinished & Q(due_date=today)),
        "upcoming": ("Upcoming", unfinished & Q(due_date__gt=today, due_date__lte=today + timedelta(days=7))),
        "completed": ("Completed", Q(status=Task.Status.DONE)),
        "all": ("All", Q()),
    }


def task_view_counts(user):
    return Task.objects.aggregate(**{
        key: Count("pk", filter=query) for key, (_, query) in task_view_queries(user).items()
    })


def task_payload(task):
    days = task.due_in_days
    tone = "done" if task.status == Task.Status.DONE else "overdue" if days is not None and days < 0 else "today" if days == 0 else "normal"
    if task.status == Task.Status.DONE:
        due_label = "Completed"
    elif days is None:
        due_label = "No due date"
    elif days < 0:
        due_label = f"{abs(days)} day{'s' if abs(days) != 1 else ''} overdue"
    elif days == 0:
        due_label = "Today"
    elif days == 1:
        due_label = "Tomorrow"
    else:
        due_label = f"In {days} days"
    return {
        "id": task.pk, "name": task.name, "notes": task.notes,
        "trip": task.trip.name, "assigned_to_id": task.assigned_to_id or "",
        "assigned_to": str(task.assigned_to) if task.assigned_to else "Unassigned",
        "status": task.status, "status_label": task.get_status_display(),
        "due_date": task.due_date.isoformat() if task.due_date else "",
        "due_in_display": task.due_in_display, "due_label": due_label, "tone": tone,
    }


class TaskListView(LoginRequiredMixin, ListView):
    model = Task
    template_name = "trips/task_list.html"
    context_object_name = "tasks"
    paginate_by = 50

    def get_queryset(self):
        params = self.request.GET
        views = task_view_queries(self.request.user)
        self.active_view = params.get("view", "all" if params.get("status") else "open")
        if self.active_view not in views:
            self.active_view = "open"
        queryset = Task.objects.select_related("trip", "assigned_to", "assigned_to__user").filter(views[self.active_view][1])
        self.filters = {key: params.get(key, "").strip() for key in (
            "q", "trip", "assigned_to", "status", "due_date_from", "due_date_to", "sort"
        )}
        for key in ("trip", "assigned_to"):
            value = self.filters[key]
            if key == "assigned_to" and value == "unassigned":
                queryset = queryset.filter(assigned_to__isnull=True)
            elif value:
                if value.isdecimal() and len(value) < 19:
                    queryset = queryset.filter(**{key + "_id": value})
                else:
                    queryset = queryset.none()
        if self.filters["q"]:
            queryset = queryset.filter(Q(name__icontains=self.filters["q"]) | Q(trip__name__icontains=self.filters["q"]))
        if self.filters["status"]:
            queryset = queryset.filter(status=self.filters["status"])
        self.filter_error = ""
        for key, lookup in (("due_date_from", "due_date__gte"), ("due_date_to", "due_date__lte")):
            if self.filters[key]:
                try:
                    value = forms.DateField().clean(self.filters[key])
                    queryset = queryset.filter(**{lookup: value})
                except forms.ValidationError:
                    self.filter_error = "Enter a valid date to filter tasks."
                    queryset = queryset.none()
        sorts = {
            "due": (F("due_date").asc(nulls_last=True), "pk"),
            "latest": (F("due_date").desc(nulls_last=True), "pk"),
            "name": ("name", "pk"),
            "trip": ("trip__name", F("due_date").asc(nulls_last=True), "pk"),
        }
        if self.filters["sort"] not in sorts:
            self.filters["sort"] = "due"
        return queryset.order_by(*sorts[self.filters["sort"]])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = task_view_counts(self.request.user)
        tabs = []
        for key, (label, _) in task_view_queries(self.request.user).items():
            query = self.request.GET.copy()
            for field in ("page", "status"):
                query.pop(field, None)
            query["view"] = key
            tabs.append({"key": key, "label": label, "count": counts[key], "url": "?" + query.urlencode()})
        query = self.request.GET.copy()
        query.pop("page", None)
        context.update({
            "trips": Trip.objects.order_by("start_date", "name"),
            "employees": Employee.objects.select_related("user"),
            "task_status_choices": Task.Status.choices,
            "filters": self.filters, "active_view": self.active_view, "view_tabs": tabs,
            "filters_active": any(self.filters[k] for k in ("trip", "assigned_to", "status", "due_date_from", "due_date_to")),
            "filter_error": self.filter_error,
            "current_querystring": self.request.GET.urlencode(), "page_query": query.urlencode(),
            "task_data": [task_payload(task) for task in context["tasks"]],
        })
        for task, data in zip(context["tasks"], context["task_data"]):
            task.queue = data
        return context


class TaskBulkUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "trips.change_task"

    def post(self, request):
        ids = request.POST.getlist("task_ids")
        field = request.POST.get("field")
        if not ids or len(ids) > 50 or any(not pk.isdecimal() or len(pk) > 18 for pk in ids) or field not in ("assigned_to", "status", "due_date"):
            return JsonResponse({"ok": False, "error": "Select up to 50 tasks and an action."}, status=400)
        with transaction.atomic():
            tasks = list(Task.objects.select_for_update().filter(pk__in=ids))
            if len(tasks) != len(set(ids)):
                return JsonResponse({"ok": False, "error": "Some tasks no longer exist. Refresh the page."}, status=400)
            pending = []
            for task in tasks:
                data = {"assigned_to": task.assigned_to_id or "", "status": task.status, "due_date": task.due_date or ""}
                data[field] = request.POST.get("value", "")
                form = TaskQuickUpdateForm(data, instance=task)
                if not form.is_valid():
                    return JsonResponse({"ok": False, "error": "Choose a valid value.", "errors": form.errors.get_json_data()}, status=400)
                pending.append(form)
            for form in pending:
                form.save()
        return JsonResponse({"ok": True, "updated": len(tasks)})


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["task_status_choices"] = Task.Status.choices
        context["employees"] = self.object.tasks.model._meta.get_field("assigned_to").remote_field.model.objects.select_related(
            "user"
        )
        context["trip_managers"] = Employee.objects.filter(
            roles__name__in=["Administrator", "Staff"],
        ).distinct()
        context["trip_leaders"] = Employee.objects.filter(
            roles__name="Host",
        ).distinct()
        context["trip_statuses"] = TripForm().fields["status"].queryset
        context["task_template_packs"] = TaskTemplatePack.objects.filter(is_active=True).prefetch_related(
            "task_templates"
        )
        return context


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
        pack = None
        pack_id = request.POST.get("task_template_pack")
        if pack_id:
            pack = get_object_or_404(TaskTemplatePack.objects.filter(is_active=True), pk=pack_id)
            templates = pack.task_templates.filter(is_active=True)
        else:
            templates = TaskTemplate.objects.filter(is_active=True)
        created_count = trip.apply_task_templates(
            assigned_to=assignee,
            templates=templates,
        )
        if created_count:
            if pack:
                messages.success(
                    request,
                    f"Added {created_count} tasks from {pack.name} and assigned them to {assignee}.",
                )
            else:
                messages.success(request, f"Added {created_count} tasks and assigned them to {assignee}.")
        else:
            if pack:
                messages.info(request, f"No new tasks were added from {pack.name}.")
            else:
                messages.info(request, "No new tasks were added. Active templates were already applied.")
        return redirect(trip)


class TaskStatusUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "trips.change_task"

    def post(self, request, trip_pk, task_pk):
        trip = get_object_or_404(Trip, pk=trip_pk)
        task = get_object_or_404(Task, pk=task_pk, trip=trip)
        form = TaskQuickUpdateForm(request.POST, instance=task)
        if not form.is_valid():
            messages.error(request, "Please fix the task assignment, status, or due date and try again.")
            return redirect(trip)
        task = form.save()
        messages.success(request, f"Updated {task.name}.")
        return redirect(trip)


class TaskQuickUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "trips.change_task"

    @transaction.atomic
    def post(self, request, pk):
        task = get_object_or_404(Task.objects.select_for_update(of=("self",)).select_related("trip", "assigned_to__user"), pk=pk)
        data = {"assigned_to": task.assigned_to_id or "", "status": task.status,
                "due_date": task.due_date or "", "name": task.name, "notes": task.notes}
        data.update({key: request.POST[key] for key in data if key in request.POST})
        form = TaskWorkspaceUpdateForm(data, instance=task)
        wants_json = request.headers.get("x-requested-with") == "XMLHttpRequest"
        if not form.is_valid():
            if wants_json:
                return JsonResponse(
                    {
                        "ok": False,
                        "errors": form.errors.get_json_data(),
                    },
                    status=400,
                )
            messages.error(request, "Please fix the task assignment, status, or due date and try again.")
        else:
            task = form.save()
            if wants_json:
                return JsonResponse({"ok": True, "task": task_payload(task), "counts": task_view_counts(request.user)})
            messages.success(request, f"Updated {task.name}.")
        return redirect(request.POST.get("next") or "task_list")


class BulkTaskStatusUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "trips.change_task"

    def post(self, request, pk):
        trip = get_object_or_404(Trip, pk=pk)
        status = request.POST.get("status")
        if status not in Task.Status.values:
            messages.error(request, "Choose a valid bulk task status.")
            return redirect(trip)

        task_ids = [task_id for task_id in request.POST.getlist("task_ids") if task_id.isdigit()]
        tasks = list(Task.objects.filter(trip=trip, pk__in=task_ids))
        if not tasks:
            messages.info(request, "Select at least one task to update.")
            return redirect(trip)

        for task in tasks:
            task.status = status
        Task.objects.bulk_update(tasks, ["status", "updated_at"])
        messages.success(request, f"Updated {len(tasks)} tasks to {Task.Status(status).label}.")
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
        if self.request.GET.get("return_to") == "tasks":
            return reverse_lazy("task_list")
        return self.object.trip.get_absolute_url()


class TaskTemplateListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = TaskTemplate
    template_name = "trips/task_template_list.html"
    context_object_name = "task_templates"
    permission_required = "trips.view_tasktemplate"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["task_template_packs"] = TaskTemplatePack.objects.prefetch_related("task_templates")
        return context


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


class TaskTemplatePackCreateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = TaskTemplatePack
    form_class = TaskTemplatePackForm
    template_name = "trips/form.html"
    permission_required = "trips.add_tasktemplate"
    success_url = reverse_lazy("task_template_list")


class TaskTemplatePackUpdateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = TaskTemplatePack
    form_class = TaskTemplatePackForm
    template_name = "trips/form.html"
    permission_required = "trips.change_tasktemplate"
    success_url = reverse_lazy("task_template_list")


class TaskTemplatePackDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "trips.delete_tasktemplate"

    def post(self, request, pk):
        task_template_pack = get_object_or_404(TaskTemplatePack, pk=pk)
        task_template_pack.delete()
        messages.success(request, "Task template pack deleted.")
        return redirect("task_template_list")


class TaskUpdateView(FormTitleMixin, LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "trips/form.html"
    permission_required = "trips.change_task"

    def get_success_url(self):
        return self.object.trip.get_absolute_url()
