from django.urls import path

from .views import StaffCreateView, StaffListView, StaffUpdateView


urlpatterns = [
    path("", StaffListView.as_view(), name="staff_list"),
    path("new/", StaffCreateView.as_view(), name="staff_create"),
    path("<int:pk>/edit/", StaffUpdateView.as_view(), name="staff_update"),
]
