from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def decode_message(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        try:
            return bytes(int(item) for item in value).decode("utf-8", errors="replace")
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def realtime_timestamp_to_utc_iso(value: Any) -> str:
    microseconds = int(value)
    timestamp = datetime.fromtimestamp(microseconds / 1_000_000, tz=UTC)
    return timestamp.isoformat().replace("+00:00", "Z")


def journal_entry_to_record(entry: dict[str, Any]) -> dict[str, Any] | None:
    cursor = entry.get("__CURSOR")
    boot_id = entry.get("_BOOT_ID")
    message = decode_message(entry.get("MESSAGE"))

    if not cursor or not boot_id:
        return None

    timestamp_value = entry.get("__REALTIME_TIMESTAMP")
    timestamp = realtime_timestamp_to_utc_iso(timestamp_value) if timestamp_value else None

    record: dict[str, Any] = {
        "service": str(entry.get("_SYSTEMD_UNIT", "")),
        "message": message,
        "priority": str(entry.get("PRIORITY", "")),
        "boot_id": str(boot_id),
        "journal_cursor": str(cursor),
    }
    if timestamp is not None:
        record["timestamp"] = timestamp
    return record


def parse_journal_json_line(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("-- cursor:"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return journal_entry_to_record(payload)


def build_journalctl_command(
    journalctl_path: str,
    units: tuple[str, ...],
    last_cursor: str | None,
) -> list[str]:
    command = [journalctl_path, "-f", "-o", "json", "--show-cursor"]
    if last_cursor:
        command.extend(["--after-cursor", last_cursor])
    for unit in units:
        command.extend(["-u", unit])
    return command
