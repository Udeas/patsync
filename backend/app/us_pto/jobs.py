from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

_lock = threading.Lock()
_jobs: dict[str, "UsPtoJob"] = {}


@dataclass
class UsPtoJob:
    job_id: str
    name: str
    status: str = "pending"
    progress: float = 0.0
    message: str = ""
    result: dict[str, Any] | None = None
    logs: list[str] = field(default_factory=list)
    progress_range: tuple[float, float] = (0.0, 1.0)


def create_job(name: str) -> UsPtoJob:
    job = UsPtoJob(job_id=str(uuid.uuid4()), name=name)
    with _lock:
        _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> UsPtoJob | None:
    with _lock:
        return _jobs.get(job_id)


def _append_log(job: UsPtoJob, line: str) -> None:
    job.logs.append(line)


def update_job_progress(job: UsPtoJob, progress: float, message: str) -> None:
    lo, hi = job.progress_range
    job.progress = lo + max(0.0, min(1.0, progress)) * (hi - lo)
    job.message = message
    _append_log(job, message)


def run_job_async(job: UsPtoJob, runner: Callable[[UsPtoJob], dict[str, Any]]) -> None:
    def _worker() -> None:
        job.status = "running"
        try:
            job.result = runner(job)
            job.status = "completed"
            job.progress = 1.0
        except Exception as exc:
            job.status = "failed"
            job.message = str(exc)
            _append_log(job, traceback.format_exc())

    threading.Thread(target=_worker, daemon=True).start()


def run_pipeline(job: UsPtoJob) -> dict[str, Any]:
    from app.us_pto.steps.calendar_events import create_events_for_ui
    from app.us_pto.steps.email_drafts import create_drafts_for_ui
    from app.us_pto.steps.fetch_email import run_fetch_for_ui

    steps: list[tuple[str, str, Callable[[UsPtoJob], dict[str, Any]]]] = [
        ("1", "Step 1: Email Fetch", run_fetch_for_ui),
        ("2", "Step 2: Calendar", lambda j: create_events_for_ui("all", job=j)),
        ("3", "Step 3: Drafts", create_drafts_for_ui),
    ]
    results: list[dict[str, Any]] = []
    total = len(steps)

    for index, (step_key, label, fn) in enumerate(steps, start=1):
        step_lo = (index - 1) / total
        step_hi = index / total
        job.progress_range = (step_lo, step_hi)
        _append_log(job, f"Running {label}...")
        job.message = f"{label}…"
        job.progress = step_lo
        result = fn(job)
        results.append({"step": label, "step_key": step_key, **result})
        _append_log(job, result.get("message", str(result)))
        if result.get("status") == "error":
            job.progress_range = (0.0, 1.0)
            job.progress = step_hi
            return {
                "status": "error",
                "message": f"Pipeline stopped at {label}: {result.get('message', 'Unknown error')}",
                "steps": results,
                "failed_at": label,
            }

    job.progress_range = (0.0, 1.0)
    job.progress = 1.0
    job.message = "Complete pipeline finished."
    return {"status": "success", "message": "Complete pipeline finished.", "steps": results}
