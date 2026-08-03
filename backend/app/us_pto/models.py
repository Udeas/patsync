from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class UsptoTracker(SQLModel, table=True):
    __tablename__ = "uspto_tracker"

    id: Optional[int] = Field(default=None, primary_key=True)
    docket_no: str = Field(max_length=64)
    application_no: str = Field(default="", max_length=32)
    doc_code: str = Field(max_length=32)
    particulars: str = Field(default="")
    event_date: str = Field(max_length=16)
    final_due_date: Optional[date] = None
    work_status: str = Field(default="Pending", max_length=32)
    completion_date: Optional[date] = None
    calendar_event_ids: str = Field(default="")
    template_status: str = Field(default="", max_length=64)
    is_closure_done: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
