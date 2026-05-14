from datetime import date
from typing import List, Optional
from sqlmodel import SQLModel, Field
from pydantic import field_validator
import re


APPLICATION_NUMBER_PATTERN = r"^\d{6}-001$"


class ReminderRead(SQLModel):
    """Computed reminder fired on fire_on (phase 1: API/UI only)."""

    kind: str
    fire_on: date
    label: str


class ApplicationCreate(SQLModel):
    application_number: str = Field(min_length=10, max_length=10)
    application_date: date
    applicant_name: str = Field(min_length=1)
    applicant_address: str = Field(min_length=1)
    application_title: str = Field(min_length=1)
    comments: Optional[str] = None

    @field_validator("application_number")
    @classmethod
    def validate_application_number(cls, value: str) -> str:
        if not re.fullmatch(APPLICATION_NUMBER_PATTERN, value):
            raise ValueError("application_number must match format xxxxxx-001")
        return value


class ApplicationRead(SQLModel):
    id: int
    application_number: str
    application_date: date
    applicant_name: str
    applicant_address: str
    application_title: str
    application_current_status: str
    comments: Optional[str] = None
    filing_date: Optional[date] = None
    fer_response_deadline: Optional[date] = None
    upcoming_reminders: List[ReminderRead] = Field(default_factory=list)


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
    application_number: Optional[str] = None
    application_date: Optional[date] = None
    applicant_name: Optional[str] = None
    applicant_address: Optional[str] = None
    application_title: Optional[str] = None
    comments: Optional[str] = None

    @field_validator("application_number")
    @classmethod
    def validate_optional_application_number(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not re.fullmatch(APPLICATION_NUMBER_PATTERN, value):
            raise ValueError("application_number must match format xxxxxx-001")
        return value


class ApplicationStatusUpdate(SQLModel):
    status_id: int = Field(gt=0)
    application_date: date


class StatusRead(SQLModel):
    id: int
    status: str
