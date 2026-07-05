from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CursorState:
    path: Path

    @classmethod
    def from_path(cls, path: str) -> CursorState:
        return cls(Path(path))

    def load(self) -> str | None:
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        cursor = payload.get("journal_cursor")
        return str(cursor) if cursor else None

    def save(self, cursor: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump({"journal_cursor": cursor}, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, self.path)
