from pathlib import Path
from typing import Any
from huey import SqliteHuey
from highliner.core import config
from highliner.services import pipeline
from highliner.repositories.db import get_database
from highliner.repositories.dtm import Bbox
from highliner.repositories.jobs import JobStore

config.HUEY_DB.parent.mkdir(parents=True, exist_ok=True)
huey = SqliteHuey("highliner", filename=str(config.HUEY_DB))


# huey ships no type information, so its task decorator is untyped; the ignore
# keeps the wrapped function's own signature checked.
@huey.task(context=True)  # type: ignore[untyped-decorator]
def analyze_task(bbox: Bbox, region: str, data_dir: str | Path, job_id: str,
                 task: Any = None) -> None:
    store = JobStore(get_database(data_dir))
    store.update(job_id, status="running")

    def report(phase: str, done: int, total: int) -> None:
        store.update(job_id, phase=phase, done=done, total=total)

    try:
        n = pipeline.analyze_area(bbox, region, data_dir, report=report)
        store.update(job_id, status="done", phase="", message=f"{n} anchors")
    except Exception as e:  # noqa: BLE001 - record then re-raise for huey
        store.update(job_id, status="error", error=str(e))
        raise
