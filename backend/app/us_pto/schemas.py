from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkStatusUpdateRequest(BaseModel):
    updates: dict[str, str]
    completion_dates: dict[str, str] = Field(default_factory=dict)
    run_step4_for_done: bool = True


class DuplicateModeRequest(BaseModel):
    duplicate_mode: str = "all"


class StepResultResponse(BaseModel):
    status: str
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    job_id: str
    name: str
    status: str
    progress: float
    message: str
    logs: list[str]
    result: dict[str, Any] | None = None


class TrackedDocCodeItem(BaseModel):
    code: str
    calendar_profile: str
    email_template: str | None = None


class DocCodesUpdateRequest(BaseModel):
    tracked_doc_codes: list[TrackedDocCodeItem]
