from django.urls import re_path

from rca_copilot_horizon.dashboards.rca_copilot.investigation import views

urlpatterns = [
    re_path(r"^(?P<incident_id>[^/]+)/$", views.DetailView.as_view(), name="detail"),
    re_path(r"^$", views.IndexView.as_view(), name="index"),
]
