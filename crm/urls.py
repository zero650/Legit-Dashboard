from django.urls import path

from .views import (
    CustomerCreateView,
    CustomerCsvImportView,
    CustomerDeleteView,
    CustomerDetailView,
    CustomerDocumentCreateView,
    CustomerDocumentDeleteView,
    CustomerDocumentServeView,
    CustomerListView,
    CustomerNotesUpdateView,
    CustomerTripHistoryCreateView,
    CustomerTripHistoryDeleteView,
    CustomerUpdateView,
)


urlpatterns = [
    path("", CustomerListView.as_view(), name="crm_customer_list"),
    path("customers/new/", CustomerCreateView.as_view(), name="crm_customer_create"),
    path("customers/import/", CustomerCsvImportView.as_view(), name="crm_customer_import"),
    path("customers/<int:pk>/", CustomerDetailView.as_view(), name="crm_customer_detail"),
    path("customers/<int:pk>/edit/", CustomerUpdateView.as_view(), name="crm_customer_update"),
    path("customers/<int:pk>/notes/", CustomerNotesUpdateView.as_view(), name="crm_customer_notes_update"),
    path("customers/<int:pk>/delete/", CustomerDeleteView.as_view(), name="crm_customer_delete"),
    path(
        "customers/<int:customer_pk>/documents/",
        CustomerDocumentCreateView.as_view(),
        name="crm_customer_document_create",
    ),
    path(
        "customers/<int:customer_pk>/documents/<int:pk>/delete/",
        CustomerDocumentDeleteView.as_view(),
        name="crm_customer_document_delete",
    ),
    path(
        "customers/<int:customer_pk>/documents/<int:pk>/file/",
        CustomerDocumentServeView.as_view(),
        name="crm_customer_document_file",
    ),
    path(
        "customers/<int:customer_pk>/trip-history/",
        CustomerTripHistoryCreateView.as_view(),
        name="crm_customer_trip_history_create",
    ),
    path(
        "customers/<int:customer_pk>/trip-history/<int:pk>/delete/",
        CustomerTripHistoryDeleteView.as_view(),
        name="crm_customer_trip_history_delete",
    ),
]
