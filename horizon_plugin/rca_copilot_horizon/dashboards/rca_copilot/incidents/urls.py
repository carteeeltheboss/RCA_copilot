from django.urls import re_path

from rca_copilot_horizon.dashboards.rca_copilot.incidents import views

urlpatterns = [re_path(r"^$", views.IndexView.as_view(), name="index")]
