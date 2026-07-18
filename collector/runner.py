from __future__ import annotations

import selectors
import signal
import subprocess
import sys
import time

from collector.batcher import LogBatcher
from collector.client import BatchClient
from collector.config import CollectorConfig
from collector.journal import build_journalctl_command, parse_journal_json_line
from collector.state import CursorState
from rca_copilot.service import prepare_service


class JournalCollector:
    def __init__(self, config: CollectorConfig) -> None:
        self.config = config
        self.state = CursorState.from_path(config.state_file)
        self.client = BatchClient(
            url=config.backend_batch_url,
            timeout_seconds=config.request_timeout_seconds,
            max_attempts=config.retry_max_attempts,
            initial_delay_seconds=config.retry_initial_delay_seconds,
            max_delay_seconds=config.retry_max_delay_seconds,
        )
        self.batcher = LogBatcher(
            batch_size=config.batch_size,
            flush_interval_seconds=config.flush_interval_seconds,
        )
        self._stopping = False
        self._shutdown_requested = False
        self._process: subprocess.Popen[str] | None = None

    def stop(self, _signum: int, _frame: object) -> None:
        self._shutdown_requested = True
        self._stopping = True
        self._terminate_process()

    def _terminate_process(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()

    def _send_batch(self, records: list[dict[str, object]]) -> bool:
        if not records:
            return True
        if not self.client.post_batch(records):
            return False
        self.state.save(str(records[-1]["journal_cursor"]))
        return True

    def _flush_or_restore(self, records: list[dict[str, object]]) -> None:
        if self._send_batch(records):
            return
        self.batcher.records = records + self.batcher.records
        time.sleep(self.config.retry_max_delay_seconds)

    def _shutdown_process(self, process: subprocess.Popen[str]) -> int:
        self._terminate_process()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if self._shutdown_requested:
            return 0
        return process.returncode or 0

    def run(self) -> int:
        last_cursor = self.state.load()
        command = build_journalctl_command(
            self.config.journalctl_path,
            self.config.units,
            last_cursor,
        )

        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        ) as process:
            self._process = process
            if process.stdout is None:
                raise RuntimeError("journalctl stdout was not captured")

            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)

            try:
                while not self._stopping:
                    events = selector.select(timeout=0.2)
                    if not events:
                        if self.batcher.due():
                            self._flush_or_restore(self.batcher.flush())
                        if process.poll() is not None:
                            break
                        continue

                    for key, _mask in events:
                        line = key.fileobj.readline()
                        if line == "":
                            self._stopping = True
                            break
                        record = parse_journal_json_line(line)
                        if record is None:
                            continue
                        batch = self.batcher.add(record)
                        if batch is not None:
                            self._flush_or_restore(batch)
            finally:
                selector.unregister(process.stdout)
                selector.close()

            if self.batcher.records:
                self._flush_or_restore(self.batcher.flush())

            return_code = self._shutdown_process(process)
            self._process = None
            return return_code


def main() -> int:
    config = CollectorConfig.from_conf(prepare_service())
    collector = JournalCollector(config)
    signal.signal(signal.SIGINT, collector.stop)
    signal.signal(signal.SIGTERM, collector.stop)
    return collector.run()


if __name__ == "__main__":
    sys.exit(main())
