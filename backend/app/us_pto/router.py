from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import threading

from app.us_pto.config import CALENDAR_DISPLAY_NAME, CALENDAR_ID, WORK_STATUS_CHOICES
from app.us_pto.doc_codes import (
    config_for_api,
    load_doc_codes_config,
    save_doc_codes_config,
    yaml_email_template_value,
)
from app.us_pto.jobs import create_job, get_job, run_job_async, run_pipeline
from app.us_pto.config import WORK_STATUS_DONE
from app.us_pto.repository import (
    get_automation_pending,
    list_entries_for_ui,
    update_work_status_batch,
)
from app.us_pto.schemas import (
    DocCodesUpdateRequest,
    DuplicateModeRequest,
    JobStatusResponse,
    WorkStatusUpdateRequest,
)
from app.us_pto.steps.calendar_events import (
    create_events_for_ui,
    get_creation_candidates_for_ui,
    get_master_file_lock_status as get_step2_lock_status,
)
from app.us_pto.steps.close_status import run_close_status_for_ui
from app.us_pto.steps.email_drafts import (
    create_drafts_for_ui,
    get_draft_candidates_for_ui,
    get_master_file_lock_status as get_step3_lock_status,
)
from app.us_pto.steps.fetch_email import run_fetch_for_ui
from app.us_pto.auth.calendar import get_calendar_service
from app.us_pto.auth.gmail import get_gmail_service

router = APIRouter()


@router.get("/config")
def get_config():
    return {
        "calendar_id": CALENDAR_ID,
        "calendar_display_name": CALENDAR_DISPLAY_NAME,
        "work_status_choices": WORK_STATUS_CHOICES,
        "scripts": [
            {"key": "step-1", "label": "Step-1: Email Fetch & Import"},
            {"key": "step-2", "label": "Step-2: Create Google Calendar events"},
            {"key": "step-3", "label": "Step-3: Generate email drafts"},
            {"key": "step-4", "label": "Step-4: Mark closed items and update calendar"},
        ],
    }


@router.get("/doc-codes")
def get_doc_codes():
    try:
        return config_for_api()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/doc-codes")
def put_doc_codes(body: DocCodesUpdateRequest):
    try:
        config = load_doc_codes_config()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    existing_by_code = {
        str(item.get("code", "")).strip().upper(): item
        for item in config.get("tracked_doc_codes", [])
    }
    updated_tracked = []
    for item in body.tracked_doc_codes:
        code = item.code.strip().upper()
        existing = existing_by_code.get(code)
        if existing is not None:
            email_template = existing.get("email_template")
        else:
            email_template = None
        updated_tracked.append(
            {
                "code": code,
                "calendar_profile": item.calendar_profile.strip(),
                "email_template": yaml_email_template_value(email_template),
            }
        )
    config["tracked_doc_codes"] = updated_tracked
    try:
        save_doc_codes_config(config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return config_for_api()


@router.get("/entries")
def get_entries(
    project_code: str = Query(""),
    doc_code: str = Query(""),
    work_status: str = Query(""),
    closed: bool = Query(False),
):
    return list_entries_for_ui(
        project_code=project_code,
        doc_code=doc_code,
        work_status=work_status,
        closed=closed,
    )


@router.get("/automation/pending")
def automation_pending():
    return get_automation_pending()


@router.patch("/entries/work-status")
def patch_work_status(body: WorkStatusUpdateRequest):
    if not body.updates:
        return {"status": "info", "message": "No changes to save.", "step4": None}

    normalized = {int(key): value for key, value in body.updates.items()}
    completion_dates = {int(key): value for key, value in body.completion_dates.items()}
    for entry_id, status in normalized.items():
        if status == WORK_STATUS_DONE and entry_id not in completion_dates:
            raise HTTPException(
                status_code=400,
                detail=f"Completion date required for Done status (entry {entry_id}).",
            )
    update_work_status_batch(normalized, completion_dates=completion_dates)
    step4_result = None
    if body.run_step4_for_done:
        done_ids = [eid for eid, status in normalized.items() if status == WORK_STATUS_DONE]
        if done_ids:

            def _close_in_background() -> None:
                run_close_status_for_ui(entry_ids=done_ids)

            threading.Thread(target=_close_in_background, daemon=True).start()
            step4_result = {
                "status": "started",
                "message": "Closing future calendar events in the background.",
            }

    return {
        "status": "success",
        "message": f"Saved {len(normalized)} row(s).",
        "step4": step4_result,
    }


@router.post("/automation/step-1/run")
def run_step_1():
    job = create_job("Step 1: Email Fetch")
    run_job_async(job, run_fetch_for_ui)
    return {"job_id": job.job_id}


@router.post("/automation/step-4/run")
def run_step_4():
    return run_close_status_for_ui()


@router.post("/automation/pipeline/run")
def run_complete_pipeline():
    job = create_job("Complete Pipeline")
    run_job_async(job, run_pipeline)
    return {"job_id": job.job_id}


@router.get("/automation/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job.job_id,
        name=job.name,
        status=job.status,
        progress=job.progress,
        message=job.message,
        logs=job.logs,
        result=job.result,
    )


@router.post("/automation/step-2/authorize")
def authorize_step_2():
    try:
        get_calendar_service()
        return {"status": "success", "message": "Calendar authorization successful."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/automation/step-2/lock-status")
def step_2_lock_status():
    return get_step2_lock_status()


@router.post("/automation/step-2/preview")
def step_2_preview(body: DuplicateModeRequest):
    return get_creation_candidates_for_ui(body.duplicate_mode)


@router.post("/automation/step-2/create")
def step_2_create(body: DuplicateModeRequest):
    job = create_job("Step 2: Calendar events")
    duplicate_mode = body.duplicate_mode
    run_job_async(job, lambda j: create_events_for_ui(duplicate_mode, job=j))
    return {"job_id": job.job_id}


@router.post("/automation/step-3/authorize")
def authorize_step_3():
    try:
        get_gmail_service()
        return {"status": "success", "message": "Gmail authorization successful."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/automation/step-3/lock-status")
def step_3_lock_status():
    return get_step3_lock_status()


@router.post("/automation/step-3/preview")
def step_3_preview():
    return get_draft_candidates_for_ui()


@router.post("/automation/step-3/create")
def step_3_create():
    job = create_job("Step 3: Gmail drafts")
    run_job_async(job, create_drafts_for_ui)
    return {"job_id": job.job_id}


@router.post("/automation/step-{step_key}/run")
def run_step_direct(step_key: str):
    if step_key == "1":
        job = create_job("Step 1")
        run_job_async(job, lambda _: run_fetch_for_ui())
        return {"job_id": job.job_id}
    if step_key == "2":
        return create_events_for_ui("all")
    if step_key == "3":
        return create_drafts_for_ui()
    if step_key == "4":
        return run_close_status_for_ui()
    raise HTTPException(status_code=404, detail="Unknown step")
