from datetime import date, datetime
from typing import List, Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel
import re

from app.tm_class_catalog import validate_tm_class_value
from app.patents.schemas import PatentAgentSummary, PatentClientSummary

APPLICATION_NUMBER_PATTERN = r"^\d{7}$"
PROJECT_CODE_PATTERN = r"^[A-Za-z0-9]+$"


class TmReminderRead(SQLModel):
    kind: str
    fire_on: date
    label: str


def _validate_project_code(value: str) -> str:
    if not re.fullmatch(PROJECT_CODE_PATTERN, value):
        raise ValueError("project_code must be alphanumeric (letters and digits only)")
    return value


class TmApplicationCreate(SQLModel):
    project_code: str = Field(min_length=1, max_length=64)
    application_number: str = Field(min_length=7, max_length=7)
    application_date: date
    applicant_name: str = Field(min_length=1)
    tm_name: str = Field(min_length=1)
    tm_class: str = Field(min_length=1)
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    applicant_address: str = Field(min_length=1)
    comments: Optional[str] = None

    @field_validator("application_number")
    @classmethod
    def validate_application_number(cls, value: str) -> str:
        if not re.fullmatch(APPLICATION_NUMBER_PATTERN, value):
            raise ValueError("application_number must be exactly 7 digits")
        return value

    @field_validator("project_code")
    @classmethod
    def validate_create_project_code(cls, value: str) -> str:
        return _validate_project_code(value)

    @field_validator("tm_class")
    @classmethod
    def validate_tm_class(cls, value: str) -> str:
        return validate_tm_class_value(value)

    @field_validator("comments")
    @classmethod
    def validate_comments_for_multi_class(cls, value: Optional[str], info) -> Optional[str]:
        tm_class = (info.data.get("tm_class") or "").strip()
        comment = (value or "").strip()
        if tm_class == "99" and not comment:
            raise ValueError("For class 99, add all classes in comments.")
        return value


class TmApplicationRead(SQLModel):
    id: int
    project_code: str
    application_number: str
    application_date: date
    status_date: date
    applicant_name: str
    tm_name: str
    tm_class: str
    tm_class_description: Optional[str] = None
    applicant_address: str
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    client: Optional[PatentClientSummary] = None
    attorney: Optional[PatentAgentSummary] = None
    application_current_status: str
    comments: Optional[str] = None
    filing_date: Optional[date] = None
    fer_followup_due: Optional[date] = None
    hearing_due: Optional[date] = None
    upcoming_reminders: List[TmReminderRead] = Field(default_factory=list)
    last_status_updated_at: Optional[datetime] = None


class TmApplicationTimelineEventRead(SQLModel):
    state_id: int
    status: str
    application_date: date


class TmApplicationTimelineRead(SQLModel):
    application_number: str
    filing_date: Optional[date]
    fer_followup_due: Optional[date]
    hearing_due: Optional[date]
    upcoming_reminders: List[TmReminderRead] = Field(default_factory=list)
    events: List[TmApplicationTimelineEventRead] = Field(default_factory=list)


class TmApplicationUpdate(SQLModel):
    project_code: Optional[str] = None
    application_number: Optional[str] = None
    application_date: Optional[date] = None
    applicant_name: Optional[str] = None
    tm_name: Optional[str] = None
    tm_class: Optional[str] = None
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    applicant_address: Optional[str] = None
    comments: Optional[str] = None

    @field_validator("application_number")
    @classmethod
    def validate_optional_application_number(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not re.fullmatch(APPLICATION_NUMBER_PATTERN, value):
            raise ValueError("application_number must be exactly 7 digits")
        return value

    @field_validator("project_code")
    @classmethod
    def validate_optional_project_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_project_code(value)

    @field_validator("tm_class")
    @classmethod
    def validate_optional_tm_class(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return validate_tm_class_value(value)


class TmApplicationStatusUpdate(SQLModel):
    status_id: int = Field(gt=0)
    application_date: date


class TmStatusRead(SQLModel):
    id: int
    status: str


class TmProjectTimelineItem(SQLModel):
    status_id: int
    status_name: str
    application_date: Optional[date] = None
    is_optional: bool = False
    is_enabled: bool = True


class TmProjectDetailRead(SQLModel):
    id: int
    project_code: str
    application_number: str
    application_date: date
    applicant_name: str
    tm_name: str
    tm_class: str
    tm_class_description: Optional[str] = None
    applicant_address: str
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    client: Optional[PatentClientSummary] = None
    attorney: Optional[PatentAgentSummary] = None
    application_current_status: str
    comments: Optional[str] = None
    timeline: list[TmProjectTimelineItem]


class TmTimelineStatusUpdate(SQLModel):
    status_id: int = Field(gt=0)
    application_date: date


class TmProjectDetailUpdate(SQLModel):
    application: TmApplicationUpdate
    timeline_updates: list[TmTimelineStatusUpdate] = Field(default_factory=list)
