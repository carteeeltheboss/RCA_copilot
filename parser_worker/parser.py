from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any


UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
REQUEST_ID_PATTERN = re.compile(r"\b(req-[0-9a-fA-F-]{36})\b")
ANSI_PATTERN = re.compile(
    r"(?:\x1b\][^\x07]*(?:\x07|\x1b\\))|(?:\x1b[@-Z\\-_])|(?:\x1b\[[0-?]*[ -/]*[@-~])"
)
LEVEL_PATTERN = re.compile(r"\b(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|TRACE)\b")
OPENSTACK_PREFIX_PATTERN = re.compile(
    r"^\S+\s+\S+\s+(?P<pid>\d+)\s+(?P<level>DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|TRACE)\s+"
    r"(?P<module>[A-Za-z_][\w.:-]*)",
    re.MULTILINE,
)
HOST_PATTERN = re.compile(r"\b(?:host|hostname)=([A-Za-z0-9_.-]+)\b")
TRACEBACK_FILE_PATTERN = re.compile(
    r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<function>[^\s]+)'
)
FILE_LINE_PATTERN = re.compile(
    r"\b(?P<file>[A-Za-z0-9_./-]+\.py):(?P<line>\d+)(?:\s+in\s+(?P<function>[A-Za-z_][\w.]*))?"
)

PRIORITY_TO_LEVEL = {
    "0": "CRITICAL",
    "1": "CRITICAL",
    "2": "CRITICAL",
    "3": "ERROR",
    "4": "WARNING",
    "5": "INFO",
    "6": "INFO",
    "7": "DEBUG",
}


def strip_ansi(value: str) -> str:
    return ANSI_PATTERN.sub("", value)


def extract_request_id(message: str) -> str | None:
    match = REQUEST_ID_PATTERN.search(message)
    if match is None:
        return None
    return match.group(1)


def extract_resource_ids(message: str, request_id: str | None) -> list[str]:
    request_uuid = request_id[4:].lower() if request_id else None
    seen: set[str] = set()
    resource_ids: list[str] = []

    for match in UUID_PATTERN.finditer(message):
        value = match.group(0).lower()
        if value == request_uuid or value in seen:
            continue
        seen.add(value)
        resource_ids.append(value)

    return resource_ids


def _first_present(document: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = document.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_level(message: str, priority: Any) -> str | None:
    prefix = OPENSTACK_PREFIX_PATTERN.search(message)
    if prefix is not None:
        level = prefix.group("level")
        return "WARNING" if level == "WARN" else level

    level = LEVEL_PATTERN.search(message)
    if level is not None:
        value = level.group(1)
        return "WARNING" if value == "WARN" else value

    return PRIORITY_TO_LEVEL.get(str(priority))


def _extract_module(message: str) -> str | None:
    prefix = OPENSTACK_PREFIX_PATTERN.search(message)
    if prefix is not None:
        return prefix.group("module")

    module_match = re.search(r"\bmodule=([A-Za-z_][\w.:-]*)\b", message)
    if module_match is not None:
        return module_match.group(1)

    return None


def _extract_pid(document: dict[str, Any], message: str) -> int | None:
    value = _first_present(document, ("pid", "_PID", "process_id"))
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    prefix = OPENSTACK_PREFIX_PATTERN.search(message)
    if prefix is None:
        return None
    return int(prefix.group("pid"))


def _extract_host(document: dict[str, Any], message: str) -> str | None:
    host = _first_present(document, ("host", "_HOSTNAME", "hostname"))
    if host is not None:
        return str(host)

    host_match = HOST_PATTERN.search(message)
    if host_match is not None:
        return host_match.group(1)

    return None


def _extract_source_location(message: str) -> tuple[str | None, int | None, str | None]:
    traceback_match = TRACEBACK_FILE_PATTERN.search(message)
    if traceback_match is not None:
        return (
            traceback_match.group("file"),
            int(traceback_match.group("line")),
            traceback_match.group("function"),
        )

    file_line_match = FILE_LINE_PATTERN.search(message)
    if file_line_match is not None:
        line = int(file_line_match.group("line"))
        return (
            file_line_match.group("file"),
            line,
            file_line_match.group("function"),
        )

    return None, None, None


def parse_raw_log(document: dict[str, Any], parser_version: str) -> dict[str, Any]:
    parsed_at = datetime.now(UTC)
    base = {
        "source_log_id": document.get("_id"),
        "service": document.get("service") or document.get("unit") or document.get("_SYSTEMD_UNIT"),
        "message": None,
        "priority": document.get("priority") or document.get("PRIORITY"),
        "timestamp": document.get("timestamp") or document.get("__REALTIME_TIMESTAMP"),
        "received_at": document.get("received_at"),
        "parser_version": parser_version,
        "parsed_at": parsed_at,
        "parse_status": "success",
        "level": None,
        "module": None,
        "request_id": None,
        "resource_ids": [],
        "host": None,
        "pid": None,
        "function": None,
        "file": None,
        "line": None,
        "parse_error": None,
    }

    try:
        raw_message = document["message"]
        if not isinstance(raw_message, str):
            raise ValueError("message must be a string")

        message = strip_ansi(raw_message)
        request_id = extract_request_id(message)
        file_name, line, function = _extract_source_location(message)

        base.update(
            {
                "message": message,
                "level": _extract_level(message, base["priority"]),
                "module": _extract_module(message),
                "request_id": request_id,
                "resource_ids": extract_resource_ids(message, request_id),
                "host": _extract_host(document, message),
                "pid": _extract_pid(document, message),
                "function": function,
                "file": file_name,
                "line": line,
            }
        )
    except Exception as exc:
        base["message"] = strip_ansi(str(document.get("message", "")))
        base["parse_status"] = "failure"
        base["parse_error"] = str(exc)

    return base

