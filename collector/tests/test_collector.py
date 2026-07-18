from __future__ import annotations

from pathlib import Path

import httpx

from collector import runner
from collector.batcher import LogBatcher
from collector.client import BatchClient
from collector.config import CollectorConfig
from collector.journal import (
    decode_message,
    journal_entry_to_record,
    realtime_timestamp_to_utc_iso,
)
from collector.state import CursorState


def test_decode_message_accepts_string() -> None:
    assert decode_message("raw log line") == "raw log line"


def test_decode_message_accepts_byte_array_list() -> None:
    assert decode_message([110, 111, 118, 97, 10]) == "nova\n"


def test_realtime_timestamp_to_utc_iso() -> None:
    assert realtime_timestamp_to_utc_iso("1719835200123456") == "2024-07-01T12:00:00.123456Z"


def test_journal_entry_to_record_extracts_required_fields() -> None:
    record = journal_entry_to_record(
        {
            "_SYSTEMD_UNIT": "devstack@n-api.service",
            "MESSAGE": [111, 107],
            "PRIORITY": "3",
            "__REALTIME_TIMESTAMP": "1719835200000000",
            "_BOOT_ID": "boot-1",
            "__CURSOR": "cursor-1",
        }
    )

    assert record == {
        "service": "devstack@n-api.service",
        "message": "ok",
        "priority": "3",
        "timestamp": "2024-07-01T12:00:00Z",
        "boot_id": "boot-1",
        "journal_cursor": "cursor-1",
    }


def test_batcher_flushes_at_size() -> None:
    batcher = LogBatcher(batch_size=2, flush_interval_seconds=10, clock=lambda: 0)

    assert batcher.add({"journal_cursor": "cursor-1"}) is None
    assert batcher.add({"journal_cursor": "cursor-2"}) == [
        {"journal_cursor": "cursor-1"},
        {"journal_cursor": "cursor-2"},
    ]
    assert batcher.records == []


def test_batcher_flushes_when_interval_elapsed() -> None:
    now = 0.0

    def clock() -> float:
        return now

    batcher = LogBatcher(batch_size=50, flush_interval_seconds=2, clock=clock)
    batcher.add({"journal_cursor": "cursor-1"})
    now = 2.1

    assert batcher.due() is True
    assert batcher.flush() == [{"journal_cursor": "cursor-1"}]


def test_cursor_state_persists_cursor(tmp_path: Path) -> None:
    state = CursorState(tmp_path / "state.json")

    assert state.load() is None
    state.save("cursor-1")

    assert state.load() == "cursor-1"


def test_batch_client_retries_until_success(monkeypatch) -> None:
    attempts = []
    sleeps = []

    def fake_post(url: str, json: dict, headers: dict | None, timeout: float) -> httpx.Response:
        attempts.append((url, json, headers, timeout))
        if len(attempts) == 1:
            raise httpx.ConnectError("temporary failure")
        return httpx.Response(
            200, json={"received_count": 1, "inserted_count": 1, "duplicate_count": 0}
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    client = BatchClient(
        url="http://127.0.0.1:8000/logs/batch",
        timeout_seconds=3,
        max_attempts=3,
        initial_delay_seconds=0.5,
        max_delay_seconds=2,
        service_token="collector-token",
        sleep=sleeps.append,
    )

    assert client.post_batch([{"journal_cursor": "cursor-1"}]) is True
    assert len(attempts) == 2
    assert attempts[-1][2] == {"X-RCA-Service-Token": "collector-token"}
    assert sleeps == [0.5]


def test_batch_client_stops_after_bounded_attempts(monkeypatch) -> None:
    attempts = []
    sleeps = []

    def fake_post(url: str, json: dict, headers: dict | None, timeout: float) -> httpx.Response:
        attempts.append((url, json, headers, timeout))
        return httpx.Response(503)

    monkeypatch.setattr(httpx, "post", fake_post)

    client = BatchClient(
        url="http://127.0.0.1:8000/logs/batch",
        timeout_seconds=3,
        max_attempts=3,
        initial_delay_seconds=0.5,
        max_delay_seconds=1,
        sleep=sleeps.append,
    )

    assert client.post_batch([{"journal_cursor": "cursor-1"}]) is False
    assert len(attempts) == 3
    assert sleeps == [0.5, 1.0]


def test_collector_stop_terminates_active_journalctl(tmp_path: Path) -> None:
    collector = runner.JournalCollector(CollectorConfig(state_file=str(tmp_path / "cursor.json")))

    class FakeProcess:
        returncode = None

        def __init__(self) -> None:
            self.terminated = False

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

    process = FakeProcess()
    collector._process = process  # type: ignore[assignment]

    collector.stop(15, None)

    assert collector._shutdown_requested is True
    assert collector._stopping is True
    assert process.terminated is True


def test_collector_shutdown_flushes_pending_batch_and_exits_zero(
    monkeypatch, tmp_path: Path
) -> None:
    sent_batches = []

    class FakeClient:
        def post_batch(self, records: list[dict[str, object]]) -> bool:
            sent_batches.append(records)
            return True

    class FakeStdout:
        pass

    class FakeProcess:
        stdout = FakeStdout()
        stderr = None
        returncode = None

        def __init__(self, *_args, **_kwargs) -> None:
            self.terminated = False

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = -15

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode or 0

        def kill(self) -> None:
            self.returncode = -9

    class FakeSelector:
        def register(self, _fileobj, _events) -> None:
            return None

        def unregister(self, _fileobj) -> None:
            return None

        def close(self) -> None:
            return None

    fake_process = FakeProcess()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *_args, **_kwargs: fake_process)
    monkeypatch.setattr(runner.selectors, "DefaultSelector", FakeSelector)

    state_file = tmp_path / "cursor.json"
    collector = runner.JournalCollector(CollectorConfig(state_file=str(state_file)))
    collector.client = FakeClient()  # type: ignore[assignment]
    collector.batcher.add(
        {
            "journal_cursor": "cursor-1",
            "boot_id": "boot-1",
            "message": "pending",
        }
    )
    collector._shutdown_requested = True
    collector._stopping = True

    assert collector.run() == 0
    assert fake_process.terminated is True
    assert sent_batches == [
        [
            {
                "journal_cursor": "cursor-1",
                "boot_id": "boot-1",
                "message": "pending",
            }
        ]
    ]
    assert CursorState(state_file).load() == "cursor-1"
