from highliner.repositories.db import Database
from highliner.repositories.jobs import JobStore


def test_create_get_update(jobstore: JobStore) -> None:
    jid = jobstore.create(name="Rocacorba", region="rocacorba")
    job = jobstore.get(jid)
    assert job is not None
    assert job["status"] == "queued"
    assert job["name"] == "Rocacorba"
    assert job["region"] == "rocacorba"
    assert job["done"] == 0 and job["total"] == 0

    jobstore.update(jid, status="running", phase="downloading", done=3, total=10)
    job = jobstore.get(jid)
    assert job is not None
    assert job["status"] == "running"
    assert job["phase"] == "downloading"
    assert job["done"] == 3 and job["total"] == 10


def test_get_unknown_is_none(jobstore: JobStore) -> None:
    assert jobstore.get("nope") is None


def test_list_newest_first(jobstore: JobStore) -> None:
    a = jobstore.create("A", "a")
    b = jobstore.create("B", "b")
    ids = [j["id"] for j in jobstore.list()]
    assert ids[0] == b and ids[1] == a


def test_reopen_persists(database: Database) -> None:
    store = JobStore(database)
    jid = store.create("A", "a")
    reopened = store.get(jid)
    assert reopened is not None
    assert reopened["name"] == "A"
