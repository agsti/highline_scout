import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_COLUMNS = ("id", "name", "region", "status", "phase", "done", "total",
            "message", "error", "created")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    region  TEXT NOT NULL,
    status  TEXT NOT NULL,
    phase   TEXT NOT NULL DEFAULT '',
    done    INTEGER NOT NULL DEFAULT 0,
    total   INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    error   TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL
)
"""


class JobStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(_SCHEMA)

    def _conn(self):
        c = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def create(self, name: str, region: str) -> str:
        jid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute(
                "INSERT INTO jobs (id, name, region, status, created) "
                "VALUES (?, ?, ?, 'queued', ?)",
                (jid, name, region, datetime.now(timezone.utc).isoformat()))
        return jid

    def get(self, job_id: str):
        with self._conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE id = ?",
                            (job_id,)).fetchone()
        return dict(row) if row else None

    def list(self):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM jobs ORDER BY created DESC, rowid DESC").fetchall()
        return [dict(r) for r in rows]

    def update(self, job_id: str, **fields):
        allowed = {k: v for k, v in fields.items()
                   if k in _COLUMNS and k != "id"}
        if not allowed:
            return
        cols = ", ".join(f"{k} = ?" for k in allowed)
        with self._conn() as c:
            c.execute(f"UPDATE jobs SET {cols} WHERE id = ?",
                      (*allowed.values(), job_id))
