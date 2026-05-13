from django.urls import path

from .views import (
    ApplyTaskTemplatesView,
    BulkTaskStatusUpdateView,
    TaskCreateView,
    TaskListView,
    TaskQuickUpdateView,
    TaskStatusUpdateView,
    TaskTemplateCreateView,
    TaskTemplateDeleteView,
    TaskTemplateListView,
    TaskTemplatePackCreateView,
    TaskTemplatePackDeleteView,
    TaskTemplatePackUpdateView,
    TaskTemplateReorderView,
    TaskTemplateUpdateView,
    TaskUpdateView,
    TripCreateView,
    TripDashboardView,
    TripDetailView,
    TripListView,
    TripQuickUpdateView,
    TripUpdateView,
)


urlpatterns = [
    path("", TripDashboardView.as_view(), name="trip_dashboard"),
    path("trips/", TripListView.as_view(), name="trip_list"),
    path("trips/<int:pk>/quick-update/", TripQuickUpdateView.as_view(), name="trip_quick_update"),
    path("tasks/", TaskListView.as_view(), name="task_list"),
    path("trips/new/", TripCreateView.as_view(), name="trip_create"),
    path("trips/<int:pk>/", TripDetailView.as_view(), name="trip_detail"),
    path("trips/<int:pk>/edit/", TripUpdateView.as_view(), name="trip_update"),
    path(
        "trips/<int:pk>/apply-task-templates/",
        ApplyTaskTemplatesView.as_view(),
        name="trip_apply_task_templates",
    ),
    path(
        "trips/<int:pk>/tasks/bulk-status/",
        BulkTaskStatusUpdateView.as_view(),
        name="trip_bulk_task_status_update",
    ),
    path(
        "trips/<int:trip_pk>/tasks/<int:task_pk>/status/",
        TaskStatusUpdateView.as_view(),
        name="trip_task_status_update",
    ),
    path("tasks/new/", TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/quick-update/", TaskQuickUpdateView.as_view(), name="task_quick_update"),
    path("tasks/<int:pk>/edit/", TaskUpdateView.as_view(), name="task_update"),
    path("task-templates/", TaskTemplateListView.as_view(), name="task_template_list"),
    path("task-templates/new/", TaskTemplateCreateView.as_view(), name="task_template_create"),
    path(
        "task-template-packs/new/",
        TaskTemplatePackCreateView.as_view(),
        name="task_template_pack_create",
    ),
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
    path(
        "task-template-packs/<int:pk>/edit/",
        TaskTemplatePackUpdateView.as_view(),
        name="task_template_pack_update",
    ),
    path(
        "task-template-packs/<int:pk>/delete/",
        TaskTemplatePackDeleteView.as_view(),
        name="task_template_pack_delete",
    ),
]
