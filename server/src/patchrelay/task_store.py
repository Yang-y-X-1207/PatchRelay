from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from patchrelay.git_workspace import resolve_state_dir


class TaskStoreError(RuntimeError):
    pass


class SQLiteTaskStore:
    def __init__(self, repo_path: Path, state_dir: Path) -> None:
        self.state_dir = resolve_state_dir(repo_path.resolve(), state_dir).resolve()
        self.db_path = self.state_dir / "tasks.sqlite"
        self._lock = threading.Lock()

    def initialize(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at)")

    def load_tasks(self) -> list[dict[str, Any]]:
        if not self.db_path.exists():
            return []
        with self._lock:
            with self._connect() as connection:
                rows = connection.execute("SELECT payload FROM tasks ORDER BY updated_at DESC").fetchall()
        payloads: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except json.JSONDecodeError as exc:
                raise TaskStoreError(f"Invalid task payload in {self.db_path}") from exc
            if isinstance(payload, dict):
                payloads.append(payload)
        return payloads

    def save_task(self, payload: dict[str, Any]) -> None:
        task_id = payload["id"]
        status = payload["status"]
        updated_at = payload["updated_at"]
        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO tasks (id, status, updated_at, payload)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        status = excluded.status,
                        updated_at = excluded.updated_at,
                        payload = excluded.payload
                    """,
                    (task_id, status, updated_at, serialized),
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection
