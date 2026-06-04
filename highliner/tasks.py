from pathlib import Path
from huey import SqliteHuey
from highliner import config, pipeline
from highliner.jobstore import JobStore

huey = SqliteHuey("highliner", filename=str(config.HUEY_DB))


@huey.task(context=True)
def analyze_task(bbox, region, data_dir, job_id, task=None):
    store = JobStore(Path(data_dir) / "jobs.db")
    store.update(job_id, status="running")

    def report(phase, done, total):
        store.update(job_id, phase=phase, done=done, total=total)

    try:
        n = pipeline.analyze_area(bbox, region, data_dir, report=report)
        store.update(job_id, status="done", phase="", message=f"{n} anchors")
    except Exception as e:  # noqa: BLE001 - record then re-raise for huey
        store.update(job_id, status="error", error=str(e))
        raise
