from huey import SqliteHuey
from highliner.core import config
from highliner.services import pipeline
from highliner.repositories.db import get_database
from highliner.repositories.jobs import JobStore

config.HUEY_DB.parent.mkdir(parents=True, exist_ok=True)
huey = SqliteHuey("highliner", filename=str(config.HUEY_DB))


@huey.task(context=True)
def analyze_task(bbox, region, data_dir, job_id, task=None):
    store = JobStore(get_database(data_dir))
    store.update(job_id, status="running")

    def report(phase, done, total):
        store.update(job_id, phase=phase, done=done, total=total)

    try:
        n = pipeline.analyze_area(bbox, region, data_dir, report=report)
        store.update(job_id, status="done", phase="", message=f"{n} anchors")
    except Exception as e:  # noqa: BLE001 - record then re-raise for huey
        store.update(job_id, status="error", error=str(e))
        raise
