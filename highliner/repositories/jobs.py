import uuid
from datetime import datetime, timezone
from typing import Any

from highliner.repositories.db import Database

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
    """Persistence for analysis jobs. Takes a :class:`Database` (which owns
    where and how to connect) and is used through the ``create``/``get``/
    ``list``/``update`` methods; that the backing store is SQLite stays behind
    the Database."""

    def __init__(self, db: Database):
        self._db = db
        with self._db.connect() as c:
            c.execute(_SCHEMA)

    def create(self, name: str, region: str) -> str:
        jid = uuid.uuid4().hex
        with self._db.connect() as c:
            c.execute(
                "INSERT INTO jobs (id, name, region, status, created) "
                "VALUES (?, ?, ?, 'queued', ?)",
                (jid, name, region, datetime.now(timezone.utc).isoformat()))
        return jid

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._db.connect() as c:
            row = c.execute("SELECT * FROM jobs WHERE id = ?",
                            (job_id,)).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._db.connect() as c:
            rows = c.execute(
                "SELECT * FROM jobs ORDER BY created DESC, rowid DESC").fetchall()
        return [dict(r) for r in rows]

    def update(self, job_id: str, **fields: object) -> None:
        allowed = {k: v for k, v in fields.items()
                   if k in _COLUMNS and k != "id"}
        if not allowed:
            return
        cols = ", ".join(f"{k} = ?" for k in allowed)
        with self._db.connect() as c:
            c.execute(f"UPDATE jobs SET {cols} WHERE id = ?",
                      (*allowed.values(), job_id))
