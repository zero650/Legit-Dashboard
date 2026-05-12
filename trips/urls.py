from django.urls import path

from .views import (
    ApplyTaskTemplatesView,
    TaskCreateView,
    TaskTemplateCreateView,
    TaskTemplateDeleteView,
    TaskTemplateListView,
    TaskTemplateReorderView,
    TaskTemplateUpdateView,
    TaskUpdateView,
    TripCreateView,
    TripDashboardView,
    TripDetailView,
    TripListView,
    TripUpdateView,
)


urlpatterns = [
    path("", TripDashboardView.as_view(), name="trip_dashboard"),
    path("trips/", TripListView.as_view(), name="trip_list"),
    path("trips/new/", TripCreateView.as_view(), name="trip_create"),
    path("trips/<int:pk>/", TripDetailView.as_view(), name="trip_detail"),
    path("trips/<int:pk>/edit/", TripUpdateView.as_view(), name="trip_update"),
    path(
        "trips/<int:pk>/apply-task-templates/",
        ApplyTaskTemplatesView.as_view(),
        name="trip_apply_task_templates",
    ),
    path("tasks/new/", TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/edit/", TaskUpdateView.as_view(), name="task_update"),
    path("task-templates/", TaskTemplateListView.as_view(), name="task_template_list"),
    path("task-templates/new/", TaskTemplateCreateView.as_view(), name="task_template_create"),
    path(
        "task-templates/reorder/",
        TaskTemplateReorderView.as_view(),
        name="task_template_reorder",
    ),
    path(
        "task-templates/<int:pk>/edit/",
        TaskTemplateUpdateView.as_view(),
        name="task_template_update",
    ),
    path(
        "task-templates/<int:pk>/delete/",
        TaskTemplateDeleteView.as_view(),
        name="task_template_delete",
    ),
]
