from django.utils.translation import gettext_lazy as _

import horizon

from rca_copilot_horizon.dashboards.rca_copilot import dashboard
from rca_copilot_horizon.dashboards.rca_copilot.policy import is_admin


class Investigation(horizon.Panel):
    name = _("Investigation")
    slug = "investigation"

    def allowed(self, context):
        return is_admin(context["request"])


dashboard.RCACopilot.register(Investigation)
