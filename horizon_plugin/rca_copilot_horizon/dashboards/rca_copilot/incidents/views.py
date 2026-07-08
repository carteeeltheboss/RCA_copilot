from horizon import views

from rca_copilot_horizon.client import RCAClient, RCAClientError


class IndexView(views.HorizonTemplateView):
    template_name = "rca_copilot/incidents.html"
    page_title = "RCA Incidents"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = {
            "severity": self.request.GET.get("severity"),
            "status": self.request.GET.get("status"),
            "service": self.request.GET.get("service"),
            "start_date": self.request.GET.get("start_date"),
            "end_date": self.request.GET.get("end_date"),
            "request_id": self.request.GET.get("request_id"),
            "resource_id": self.request.GET.get("resource_id"),
            "q": self.request.GET.get("q"),
            "sort": self.request.GET.get("sort", "newest"),
            "page": self.request.GET.get("page", "1"),
            "page_size": self.request.GET.get("page_size", "25"),
        }
        try:
            context["result"] = RCAClient().get("/api/v1/incidents", params=params)
            context["backend_error"] = None
        except RCAClientError as exc:
            context["result"] = {"items": [], "total": 0, "page": 1, "page_size": 25}
            context["backend_error"] = str(exc)
        context["filters"] = params
        return context
