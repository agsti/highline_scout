import sqlite3
from functools import lru_cache
from pathlib import Path


class Database:
    """The application's database, living under a region ``data_dir``.

    Owns *where* to connect and *how* (the file location and connection
    settings), so repositories depend on a ``Database`` instead of touching
    sqlite or filesystem paths themselves. A single instance can be shared by
    several repositories; it hands out a fresh, short-lived connection per
    operation, which is the safe pattern when both request threads and the
    background worker thread touch the same store.
    """

    FILENAME = "jobs.db"

    def __init__(self, data_dir):
        self._path = Path(data_dir) / self.FILENAME
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        return c


@lru_cache(maxsize=8)
def _database(data_dir: str) -> Database:
    return Database(data_dir)


def get_database(data_dir) -> Database:
    """The single place a ``Database`` is created. Cached per ``data_dir`` so the
    API process and the in-process background worker obtain the same instance for
    a given region tree."""
    return _database(str(Path(data_dir)))
