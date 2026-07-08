from horizon import views

from rca_copilot_horizon.client import RCAClient, RCAClientError


class IndexView(views.HorizonTemplateView):
    template_name = "rca_copilot/system_health.html"
    page_title = "RCA System Health"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["health"] = RCAClient().get("/api/v1/system/health")
            context["backend_error"] = None
        except RCAClientError as exc:
            context["health"] = {"components": []}
            context["backend_error"] = str(exc)
        return context
