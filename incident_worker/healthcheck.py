from __future__ import annotations

import sys
import time
from pathlib import Path

from incident_worker.config import IncidentConfig
from rca_copilot.service import prepare_service


def main() -> int:
    config = IncidentConfig.from_conf(prepare_service())
    path = Path(config.health_file)
    if not path.exists():
        return 1

    try:
        updated_at = float(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return 1

    max_age = max(config.poll_interval_seconds * 3, 10)
    if time.time() - updated_at > max_age:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
