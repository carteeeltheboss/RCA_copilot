from django.utils.translation import gettext_lazy as _

DASHBOARD = "rca_copilot"
ADD_INSTALLED_APPS = [
    "rca_copilot_horizon",
    "rca_copilot_horizon.dashboards.rca_copilot",
]
AUTO_DISCOVER_STATIC_FILES = True

ADD_JS_FILES = ["rca_copilot/cytoscape.min.js", "rca_copilot/rca_copilot.js"]
