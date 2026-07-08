from django.utils.translation import gettext_lazy as _

import horizon


class RCACopilot(horizon.Dashboard):
    name = _("RCA Copilot")
    slug = "rca_copilot"


horizon.register(RCACopilot)
