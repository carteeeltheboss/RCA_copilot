from horizon import views

from rca_copilot_horizon.client import RCAClient, RCAClientError


class IndexView(views.HorizonTemplateView):
    template_name = "rca_copilot/overview.html"
    page_title = "RCA Copilot Overview"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["summary"] = RCAClient().get("/api/v1/system/summary")
            context["backend_error"] = None
        except RCAClientError as exc:
            context["summary"] = {}
            context["backend_error"] = str(exc)
        return context
