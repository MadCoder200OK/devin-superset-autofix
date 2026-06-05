"""
Tracker — SQLite-backed persistence for issue → Devin session mapping.
Provides the data layer for the observability dashboard.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.environ.get("DB_PATH", "data/tracker.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Tracker:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_number    INTEGER NOT NULL,
                issue_title     TEXT NOT NULL,
                issue_url       TEXT,
                issue_labels    TEXT,
                category        TEXT DEFAULT 'general',
                session_id      TEXT,
                session_url     TEXT,
                status          TEXT DEFAULT 'pending',
                pr_url          TEXT,
                error_message   TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                completed_at    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_session ON tasks(session_id);
        """
        )
        self._conn.commit()

    # ── Write ────────────────────────────────────────────────

    def create_task(
        self,
        issue_number: int,
        issue_title: str,
        issue_url: str = None,
        issue_labels: str = None,
        category: str = "general",
    ) -> int:
        now = _now()
        cur = self._conn.execute(
            """INSERT INTO tasks
               (issue_number, issue_title, issue_url, issue_labels, category,
                status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (issue_number, issue_title, issue_url, issue_labels, category, now, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_session(
        self, task_id: int, session_id: str, session_url: str
    ):
        self._conn.execute(
            """UPDATE tasks
               SET session_id=?, session_url=?, status='running', updated_at=?
               WHERE id=?""",
            (session_id, session_url, _now(), task_id),
        )
        self._conn.commit()

    def update_status(
        self,
        session_id: str,
        status: str,
        pr_url: str = None,
        error_message: str = None,
    ):
        now = _now()
        completed = now if status in ("completed", "error", "failed") else None
        self._conn.execute(
            """UPDATE tasks
               SET status=?, pr_url=COALESCE(?, pr_url),
                   error_message=COALESCE(?, error_message),
                   completed_at=COALESCE(?, completed_at),
                   updated_at=?
               WHERE session_id=?""",
            (status, pr_url, error_message, completed, now, session_id),
        )
        self._conn.commit()

    # ── Read ─────────────────────────────────────────────────

    def get_all_tasks(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_active_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM tasks WHERE status IN ('pending', 'running') ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_task_by_issue(self, issue_number: int) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE issue_number=? ORDER BY created_at DESC LIMIT 1",
            (issue_number,),
        ).fetchone()
        return dict(row) if row else None

    def get_task_by_session(self, session_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE session_id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Analytics ────────────────────────────────────────────

    def get_stats(self) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        ).fetchall()
        by_status = {r["status"]: r["cnt"] for r in rows}
        total = sum(by_status.values())
        completed = by_status.get("completed", 0)
        failed = by_status.get("error", 0) + by_status.get("failed", 0)

        # Average time to completion
        avg_row = self._conn.execute(
            """SELECT AVG(
                 (julianday(completed_at) - julianday(created_at)) * 86400
               ) as avg_seconds
               FROM tasks WHERE completed_at IS NOT NULL"""
        ).fetchone()
        avg_seconds = avg_row["avg_seconds"] if avg_row and avg_row["avg_seconds"] else None

        return {
            "total": total,
            "by_status": by_status,
            "completed": completed,
            "failed": failed,
            "running": by_status.get("running", 0),
            "pending": by_status.get("pending", 0),
            "success_rate": round(completed / total * 100, 1) if total > 0 else 0,
            "avg_completion_seconds": round(avg_seconds, 1) if avg_seconds else None,
        }
