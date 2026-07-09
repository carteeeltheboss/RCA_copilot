from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase


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

        self.assertEqual(response.status_code, 200)
        client_cls.assert_called_once_with(timeout=95)
        client_cls.return_value.post.assert_called_once_with("/api/v1/incidents/incident-1/explain")
        self.assertIn(b'"summary": "ok"', response.content)
        self.assertIn(b'"fact"', response.content)

    @patch("rca_copilot_horizon.dashboards.rca_copilot.investigation.views.RCAClient")
    def test_explain_endpoint_returns_visible_error(self, client_cls):
        from rca_copilot_horizon.client import RCAClientError
        from rca_copilot_horizon.dashboards.rca_copilot.investigation import views

        client_cls.return_value.post.side_effect = RCAClientError("provider unavailable", status=503)
        request = self.factory.post("/dashboard/rca_copilot/investigation/incident-1/explain/")

        response = views.explain(request, "incident-1")

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"AI explanation failed. Backend returned: provider unavailable", response.content)
