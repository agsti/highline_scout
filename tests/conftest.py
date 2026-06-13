import pytest

from highliner.repositories.db import Database
from highliner.repositories.jobs import JobStore


@pytest.fixture
def database(tmp_path) -> Database:
    """A Database isolated to the test's tmp_path. Single place tests obtain
    one; inject it (or the ``jobstore`` built on it) rather than constructing
    Database/JobStore by hand."""
    return Database(tmp_path)


@pytest.fixture
def jobstore(database) -> JobStore:
    return JobStore(database)
