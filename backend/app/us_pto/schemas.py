from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    # "docket_only" fetches/imports cases and saves docket entries only -
    # no Google Calendar events, no email drafts.
    mode: Literal["complete", "docket_only"] = "complete"


class WorkStatusUpdateRequest(BaseModel):
    updates: dict[str, str]
    completion_dates: dict[str, str] = Field(default_factory=dict)
    comments: dict[str, str] = Field(default_factory=dict)
    run_step4_for_done: bool = True


class DuplicateModeRequest(BaseModel):
    duplicate_mode: str = "all"
    excluded_entry_ids: list[int] = Field(default_factory=list)


class DraftCreateRequest(BaseModel):
    excluded_entry_ids: list[int] = Field(default_factory=list)


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


class DocCodeRuleItem(BaseModel):
    doc_code: str
    final_due_months: int
    final_due_extension_months: int
    email_template: str | None = None


class DocCodeRuleCreateRequest(BaseModel):
    doc_code: str
    final_due_months: int
    final_due_extension_months: int
    email_template: str | None = None


class DocCodeRuleUpdateRequest(BaseModel):
    final_due_months: int
    final_due_extension_months: int
    email_template: str | None = None
    # False (default): the new months/extension only apply to entries
    # inserted from now on. True: also recompute final_due_date on existing
    # uspto_tracker rows for this doc code (skipping ones already Done).
    apply_to_existing: bool = False
