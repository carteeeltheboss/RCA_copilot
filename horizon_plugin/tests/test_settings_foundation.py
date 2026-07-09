from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


ROOT = Path(__file__).resolve().parents[1] / "rca_copilot_horizon"


def test_settings_page_is_admin_only() -> None:
    source = (ROOT / "dashboards/rca_copilot/settings/views.py").read_text()

    assert "is_admin(request)" in source
    assert "HttpResponseForbidden" in source


def test_dashboard_and_panels_are_registered() -> None:
    dashboard = (ROOT / "dashboards/rca_copilot/dashboard.py").read_text()
    enabled = [path.name for path in (ROOT / "enabled").glob("_90*.py")]

    assert "horizon.register(RCACopilot)" in dashboard
    for expected in [
        "_9010_rca_overview.py",
        "_9020_rca_incidents.py",
        "_9030_rca_investigation.py",
        "_9040_rca_system_health.py",
        "_9050_rca_settings.py",
    ]:
        assert expected in enabled


def test_incident_list_and_investigation_pages_render_backend_data() -> None:
    incidents_view = (ROOT / "dashboards/rca_copilot/incidents/views.py").read_text()
    incidents_template = (ROOT / "templates/rca_copilot/incidents.html").read_text()
    investigation_view = (ROOT / "dashboards/rca_copilot/investigation/views.py").read_text()
    investigation_template = (ROOT / "templates/rca_copilot/investigation.html").read_text()

    assert '"/api/v1/incidents"' in incidents_view
    for expected in ["severity", "status", "service", "request_id", "resource_id", "start_date", "end_date", "q"]:
        assert f'name="{expected}"' in incidents_template
    assert '"/api/v1/incidents/{incident_id}/graph"' in investigation_view
    assert '"/api/v1/incidents/{incident_id}/timeline"' in investigation_view
    assert "correlation graph" in investigation_template.lower()


def test_graph_json_is_passed_safely_and_cytoscape_is_local() -> None:
    investigation = (ROOT / "templates/rca_copilot/investigation.html").read_text()
    script = (ROOT / "static/rca_copilot/rca_copilot.js").read_text()

    assert 'json_script:"rca-graph-data"' in investigation
    assert "cytoscape.min.js" in investigation
    assert "window.cytoscape" in script
    assert "127.0.0.1:8000" not in script
    assert "100.125.17.77" not in script
    assert "XMLHttpRequest" not in script


def test_ai_explanation_available_and_unavailable_states_exist() -> None:
    investigation_view = (ROOT / "dashboards/rca_copilot/investigation/views.py").read_text()
    investigation = (ROOT / "templates/rca_copilot/investigation.html").read_text()
    urls = (ROOT / "dashboards/rca_copilot/investigation/urls.py").read_text()
    script = (ROOT / "static/rca_copilot/rca_copilot.js").read_text()

    assert '"/api/v1/incidents/{incident_id}/explain"' in investigation_view
    assert "RCAClient(timeout=95)" in investigation_view
    assert "JsonResponse" in investigation_view
    assert "name=\"explain\"" in urls
    assert "AI-assisted explanation from bounded evidence" in investigation
    assert "id=\"rca-explain-button\"" in investigation
    assert "data-explain-url" in investigation
    assert "id=\"rca-ai-error\"" in investigation
    assert "Explain incident" in investigation
    assert "Generating explanation..." in investigation
    assert "window.fetch(url" in script
    assert "'X-CSRFToken': csrfToken()" in script
    assert "credentials: 'same-origin'" in script
    assert "AI explanation failed. Backend returned:" in script


def test_static_js_renders_ai_sections_safely() -> None:
    script = (ROOT / "static/rca_copilot/rca_copilot.js").read_text()

    for expected in ["Summary", "Likely failure area", "Evidence", "Hypotheses", "Recommended next checks", "Confidence", "Limitations"]:
        assert expected in script
    assert "escapeHtml(answer.answer_text)" in script
    assert ".innerHTML = html" in script


def test_service_token_is_only_used_server_side() -> None:
    client = (ROOT / "client.py").read_text()
    templates = "\n".join(path.read_text() for path in (ROOT / "templates/rca_copilot").glob("*.html"))
    static = "\n".join(path.read_text(errors="ignore") for path in (ROOT / "static/rca_copilot").glob("*.js"))

    assert "RCA_INTERNAL_SERVICE_TOKEN" in client
    assert "X-RCA-Service-Token" in client
    assert "RCA_INTERNAL_SERVICE_TOKEN" not in templates
    assert "X-RCA-Service-Token" not in templates
    assert "RCA_INTERNAL_SERVICE_TOKEN" not in static
    assert "X-RCA-Service-Token" not in static


class ExplainEndpointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("rca_copilot_horizon.dashboards.rca_copilot.investigation.views.RCAClient")
    def test_explain_endpoint_calls_rca_client_with_incident_id(self, client_cls):
        from rca_copilot_horizon.dashboards.rca_copilot.investigation import views

        client_cls.return_value.post.return_value = {
            "incident_id": "incident-1",
            "provider": {"provider_kind": "ollama", "model_name": "qwen2.5-coder:7b"},
            "answer": {"summary": "ok", "evidence": {"message": "fact"}},
        }
        request = self.factory.post("/dashboard/rca_copilot/investigation/incident-1/explain/")

        response = views.explain(request, "incident-1")

        assert response.status_code == 200
        client_cls.assert_called_once_with(timeout=95)
        client_cls.return_value.post.assert_called_once_with("/api/v1/incidents/incident-1/explain")
        assert b'"summary": "ok"' in response.content
        assert b'"fact"' in response.content

    @patch("rca_copilot_horizon.dashboards.rca_copilot.investigation.views.RCAClient")
    def test_explain_endpoint_returns_visible_error(self, client_cls):
        from rca_copilot_horizon.client import RCAClientError
        from rca_copilot_horizon.dashboards.rca_copilot.investigation import views

        client_cls.return_value.post.side_effect = RCAClientError("provider unavailable", status=503)
        request = self.factory.post("/dashboard/rca_copilot/investigation/incident-1/explain/")

        response = views.explain(request, "incident-1")

        assert response.status_code == 503
        assert b"AI explanation failed. Backend returned: provider unavailable" in response.content


def test_provider_list_rendering_and_actions_exist() -> None:
    template = (ROOT / "templates/rca_copilot/settings_provider_section.html").read_text()

    for expected in ["display_name", "provider_kind", "provider_type", "base_url", "model_name", "capabilities"]:
        assert expected in template
    for action in ["test", "activate", "disable", "rollback", "delete"]:
        assert f'value="{action}"' in template


def test_provider_form_validation_options_exist() -> None:
    template = (ROOT / "templates/rca_copilot/settings.html").read_text()

    for provider_type in ["llm", "embedding", "reranker", "vector_store"]:
        assert f'value="{provider_type}"' in template
    for provider_kind in ["ollama", "openai_compatible", "gemini", "anthropic", "custom_http", "chroma"]:
        assert f'value="{provider_kind}"' in template
    assert "required" in template


def test_masked_secret_and_unavailable_provider_messages_exist() -> None:
    settings = (ROOT / "templates/rca_copilot/settings.html").read_text()
    section = (ROOT / "templates/rca_copilot/settings_provider_section.html").read_text()

    assert "API keys are write-only" in settings
    assert "api_key_masked" in section
    assert "No AI provider configured. Deterministic RCA remains available." in section
    assert "AI provider unavailable. Ingestion, correlation, incident detection, and enrichment are unaffected." in section
