import json

from django.shortcuts import redirect
from horizon import views

from rca_copilot_horizon.client import RCAClient, RCAClientError


class IndexView(views.HorizonTemplateView):
    template_name = "rca_copilot/investigation_empty.html"
    page_title = "RCA Investigation"

    def get(self, request, *args, **kwargs):
        incident_id = request.GET.get("incident_id")
        if incident_id:
            return redirect("horizon:rca_copilot:investigation:detail", incident_id=incident_id)
        return super().get(request, *args, **kwargs)


class DetailView(views.HorizonTemplateView):
    template_name = "rca_copilot/investigation.html"
    page_title = "RCA Investigation"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        incident_id = kwargs["incident_id"]
        client = RCAClient()
        try:
            incident = client.get(f"/api/v1/incidents/{incident_id}")
            graph = client.get(f"/api/v1/incidents/{incident_id}/graph", params={"max_nodes": 100})
            timeline = client.get(f"/api/v1/incidents/{incident_id}/timeline")
            context.update(
                {
                    "incident": incident,
                    "graph": graph,
                    "timeline": timeline,
                    "graph_json": json.dumps(graph),
                    "backend_error": None,
                }
            )
        except RCAClientError as exc:
            context.update({"incident": {}, "graph": {}, "timeline": {"items": []}, "graph_json": "{}", "backend_error": str(exc)})
        return context
