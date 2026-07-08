from django.contrib import messages
from django.http import HttpResponseForbidden
from horizon import views

from rca_copilot_horizon.client import RCAClient, RCAClientError
from rca_copilot_horizon.dashboards.rca_copilot.policy import is_admin


class IndexView(views.HorizonTemplateView):
    template_name = "rca_copilot/settings.html"
    page_title = "RCA Copilot Settings"

    def dispatch(self, request, *args, **kwargs):
        if not is_admin(request):
            return HttpResponseForbidden("Settings requires an administrator role.")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        client = RCAClient()
        action = request.POST.get("action")
        provider_id = request.POST.get("provider_id")
        try:
            if action == "add_provider":
                payload = _provider_payload(request.POST)
                result = client.post("/api/v1/providers", payload)
                messages.success(request, "Provider draft saved.")
                self.extra_result = result
            elif action == "test" and provider_id:
                self.extra_result = client.post(f"/api/v1/providers/{provider_id}/test")
                messages.info(request, "Connection test completed.")
            elif action == "activate" and provider_id:
                self.extra_result = client.post(f"/api/v1/providers/{provider_id}/activate")
                messages.success(request, "Provider activated.")
            elif action == "disable" and provider_id:
                self.extra_result = client.post(f"/api/v1/providers/{provider_id}/disable")
                messages.info(request, "Provider disabled.")
            elif action == "rollback" and provider_id:
                version = request.POST.get("config_version")
                self.extra_result = client.post(f"/api/v1/providers/{provider_id}/rollback/{version}")
                messages.success(request, "Provider rolled back.")
            elif action == "delete" and provider_id:
                client.delete(f"/api/v1/providers/{provider_id}")
                messages.info(request, "Unused draft deleted.")
        except RCAClientError as exc:
            messages.error(request, str(exc))
            self.extra_result = {"error": str(exc)}
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = RCAClient()
        try:
            providers = client.get("/api/v1/providers").get("items", [])
            histories = {
                provider["provider_id"]: client.get(f"/api/v1/providers/{provider['provider_id']}/history").get("items", [])[:5]
                for provider in providers[:20]
            }
            context.update({"providers": providers, "histories": histories, "backend_error": None})
        except RCAClientError as exc:
            context.update({"providers": [], "histories": {}, "backend_error": str(exc)})
        context["last_action_result"] = getattr(self, "extra_result", None)
        context["sections"] = [
            "General",
            "LLM Providers",
            "Embedding Providers",
            "Reranker Providers",
            "Vector Store Providers",
            "Reliability",
            "Security",
            "Configuration History",
        ]
        return context


def _provider_payload(post):
    return {
        "provider_type": post.get("provider_type"),
        "provider_kind": post.get("provider_kind"),
        "display_name": post.get("display_name"),
        "base_url": post.get("base_url") or None,
        "model_name": post.get("model_name") or None,
        "enabled": post.get("enabled") == "on",
        "timeout_seconds": int(post.get("timeout_seconds") or 10),
        "retry_count": int(post.get("retry_count") or 0),
        "verify_tls": post.get("verify_tls") == "on",
        "api_key": post.get("api_key") or None,
        "extra_config": {},
    }
