from datetime import date, datetime
from typing import List, Optional
from sqlmodel import SQLModel, Field
from pydantic import field_validator
import re

from app.patents.schemas import PatentAgentSummary, PatentClientSummary

APPLICATION_NUMBER_PATTERN = r"^\d{6}-001$"
PROJECT_CODE_PATTERN = r"^[A-Za-z0-9]+$"


class ReminderRead(SQLModel):
    """Computed reminder fired on fire_on (phase 1: API/UI only)."""

    kind: str
    fire_on: date
    label: str


def _validate_project_code(value: str) -> str:
    if not re.fullmatch(PROJECT_CODE_PATTERN, value):
        raise ValueError("project_code must be alphanumeric (letters and digits only)")
    return value


class ApplicationCreate(SQLModel):
    project_code: str = Field(min_length=1, max_length=64)
    application_number: str = Field(min_length=10, max_length=10)
    application_date: date
    applicant_name: str = Field(min_length=1)
    applicant_address: str = Field(min_length=1)
    application_title: str = Field(min_length=1)
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    comments: Optional[str] = None

    @field_validator("application_number")
    @classmethod
    def validate_application_number(cls, value: str) -> str:
        if not re.fullmatch(APPLICATION_NUMBER_PATTERN, value):
            raise ValueError("application_number must match format xxxxxx-001")
        return value

    @field_validator("project_code")
    @classmethod
    def validate_create_project_code(cls, value: str) -> str:
        return _validate_project_code(value)


class ApplicationRead(SQLModel):
    id: int
    project_code: str
    application_number: str
    application_date: date
    status_date: date
    applicant_name: str
    applicant_address: str
    application_title: str
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    client: Optional[PatentClientSummary] = None
    attorney: Optional[PatentAgentSummary] = None
    application_current_status: str
    comments: Optional[str] = None
    filing_date: Optional[date] = None
    fer_response_deadline: Optional[date] = None
    upcoming_reminders: List[ReminderRead] = Field(default_factory=list)
    last_status_updated_at: Optional[datetime] = None


class ApplicationTimelineEventRead(SQLModel):
    """application_date semantics: event date entered for this status."""

    state_id: int
    status: str
    application_date: date


class ApplicationTimelineRead(SQLModel):
    application_number: str
    filing_date: Optional[date]
    fer_response_deadline: Optional[date]
    upcoming_reminders: List[ReminderRead] = Field(default_factory=list)
    events: List[ApplicationTimelineEventRead] = Field(default_factory=list)


class ApplicationUpdate(SQLModel):
    project_code: Optional[str] = None
    application_number: Optional[str] = None
    application_date: Optional[date] = None
    applicant_name: Optional[str] = None
    applicant_address: Optional[str] = None
    application_title: Optional[str] = None
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    comments: Optional[str] = None

    @field_validator("application_number")
    @classmethod
    def validate_optional_application_number(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not re.fullmatch(APPLICATION_NUMBER_PATTERN, value):
            raise ValueError("application_number must match format xxxxxx-001")
        return value

    @field_validator("project_code")
    @classmethod
    def validate_optional_project_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_project_code(value)


class ApplicationStatusUpdate(SQLModel):
    status_id: int = Field(gt=0)
    application_date: date


class StatusRead(SQLModel):
    id: int
    status: str


class ProjectTimelineItem(SQLModel):
    status_id: int
    status_name: str
    application_date: Optional[date] = None
    is_optional: bool = False
    is_enabled: bool = True


class ProjectDetailRead(SQLModel):
    id: int
    project_code: str
    application_number: str
    application_date: date
    applicant_name: str
    applicant_address: str
    application_title: str
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    client: Optional[PatentClientSummary] = None
    attorney: Optional[PatentAgentSummary] = None
    application_current_status: str
    comments: Optional[str] = None
    timeline: list[ProjectTimelineItem]


class TimelineStatusUpdate(SQLModel):
    status_id: int = Field(gt=0)
    application_date: date


class ProjectDetailUpdate(SQLModel):
    application: ApplicationUpdate
    timeline_updates: list[TimelineStatusUpdate] = Field(default_factory=list)
