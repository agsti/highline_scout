from highliner.jobstore import JobStore


def test_create_get_update(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    jid = store.create(name="Rocacorba", region="rocacorba")
    job = store.get(jid)
    assert job["status"] == "queued"
    assert job["name"] == "Rocacorba"
    assert job["region"] == "rocacorba"
    assert job["done"] == 0 and job["total"] == 0

    store.update(jid, status="running", phase="downloading", done=3, total=10)
    job = store.get(jid)
    assert job["status"] == "running"
    assert job["phase"] == "downloading"
    assert job["done"] == 3 and job["total"] == 10


def test_get_unknown_is_none(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    assert store.get("nope") is None


def test_list_newest_first(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    a = store.create("A", "a")
    b = store.create("B", "b")
    ids = [j["id"] for j in store.list()]
    assert ids[0] == b and ids[1] == a


def test_reopen_persists(tmp_path):
    path = tmp_path / "jobs.db"
    jid = JobStore(path).create("A", "a")
    assert JobStore(path).get(jid)["name"] == "A"
