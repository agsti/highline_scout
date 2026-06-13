from highliner.repositories.jobs import JobStore


def test_create_get_update(jobstore):
    jid = jobstore.create(name="Rocacorba", region="rocacorba")
    job = jobstore.get(jid)
    assert job["status"] == "queued"
    assert job["name"] == "Rocacorba"
    assert job["region"] == "rocacorba"
    assert job["done"] == 0 and job["total"] == 0

    jobstore.update(jid, status="running", phase="downloading", done=3, total=10)
    job = jobstore.get(jid)
    assert job["status"] == "running"
    assert job["phase"] == "downloading"
    assert job["done"] == 3 and job["total"] == 10


def test_get_unknown_is_none(jobstore):
    assert jobstore.get("nope") is None


def test_list_newest_first(jobstore):
    a = jobstore.create("A", "a")
    b = jobstore.create("B", "b")
    ids = [j["id"] for j in jobstore.list()]
    assert ids[0] == b and ids[1] == a


def test_reopen_persists(database):
    jid = JobStore(database).create("A", "a")
    assert JobStore(database).get(jid)["name"] == "A"
