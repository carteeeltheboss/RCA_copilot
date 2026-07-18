import json

from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
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
                    "ai_result": None,
                    "ai_error": None,
                }
            )
        except RCAClientError as exc:
            context.update(
                {
                    "incident": {},
                    "graph": {},
                    "timeline": {"items": []},
                    "graph_json": "{}",
                    "backend_error": str(exc),
                    "ai_result": None,
                    "ai_error": None,
                }
            )
        return context


@require_POST
def explain(request, incident_id):
    try:
        result = _normalize_ai_result(
            RCAClient(timeout=95).post(f"/api/v1/incidents/{incident_id}/explain")
        )
        return JsonResponse(result)
    except RCAClientError as exc:
        return JsonResponse(
            {
                "status": "unavailable",
                "error": f"AI explanation failed. Backend returned: {str(exc)}",
            },
            status=exc.status or 502,
        )
    except Exception:
        return JsonResponse(
            {
                "status": "error",
                "error": "AI explanation failed. Backend returned: malformed response",
            },
            status=502,
        )


def _normalize_ai_result(result):
    answer = result.get("answer") or {}
    if isinstance(answer, dict):
        for key in ("evidence", "hypotheses", "recommended_next_checks"):
            values = answer.get(key) or []
            if not isinstance(values, list):
                values = [values]
            answer[key] = [_compact_text(item) for item in values]
    return result


def _compact_text(value):
    if isinstance(value, dict):
        for key in ("summary", "hypothesis", "check", "message", "reason"):
            if value.get(key):
                return str(value[key])
        return "; ".join(
            f"{key}: {val}" for key, val in value.items() if val not in (None, "", [])
        )[:500]
    return str(value)[:500]
