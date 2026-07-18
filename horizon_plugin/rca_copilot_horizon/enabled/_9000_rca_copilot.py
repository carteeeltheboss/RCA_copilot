from django.utils.translation import gettext_lazy as _

DASHBOARD = "rca_copilot"
ADD_INSTALLED_APPS = [
    "rca_copilot_horizon",
    "rca_copilot_horizon.dashboards.rca_copilot",
]
AUTO_DISCOVER_STATIC_FILES = True

ADD_JS_FILES = ["rca_copilot/cytoscape.min.js", "rca_copilot/rca_copilot.js"]

# Deployments can override these in local_settings.py. These are Django
# settings rather than process environment variables by design.
RCA_COPILOT_BACKEND_URL = "http://127.0.0.1:8000"
RCA_COPILOT_INTERNAL_SERVICE_TOKEN = None
RCA_COPILOT_BACKEND_TIMEOUT_SECONDS = 5.0
