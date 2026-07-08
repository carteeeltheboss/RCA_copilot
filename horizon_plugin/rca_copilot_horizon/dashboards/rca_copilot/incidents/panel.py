from django.utils.translation import gettext_lazy as _

import horizon

from rca_copilot_horizon.dashboards.rca_copilot import dashboard
from rca_copilot_horizon.dashboards.rca_copilot.policy import is_admin


class Incidents(horizon.Panel):
    name = _("Incidents")
    slug = "incidents"

    def allowed(self, context):
        return is_admin(context["request"])


dashboard.RCACopilot.register(Incidents)
