from django.urls import re_path

from rca_copilot_horizon.dashboards.rca_copilot.overview import views

urlpatterns = [re_path(r"^$", views.IndexView.as_view(), name="index")]
