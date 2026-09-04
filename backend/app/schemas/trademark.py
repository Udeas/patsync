from datetime import date, datetime
from typing import List, Optional

from pydantic import field_validator, model_validator
from sqlmodel import Field, SQLModel
import re

from app.domain.custom_events import validate_reminder_option
from app.tm_class_catalog import MULTI_CLASS_MAIN_VALUE, SINGLE_CLASS_VALUES, validate_tm_class_value
from app.patents.schemas import PatentAgentSummary, PatentClientSummary

APPLICATION_NUMBER_PATTERN = r"^\d{7}$"
PROJECT_CODE_PATTERN = r"^[A-Za-z0-9]+$"
APPLICANT_TYPE_VALUES = {"MSME", "Individual", "Company"}
TM_TYPE_VALUES = {"Device/Logo", "Wordmark"}
TM_USAGE_STATUS_VALUES = {"Proposed to be used", "Used since"}


class TmReminderRead(SQLModel):
    kind: str
    fire_on: date
    label: str


class TmClassDescriptionEntry(SQLModel):
    class_no: str
    description: str = ""


class TmProjectNoteRead(SQLModel):
    id: int
    note_text: str
    created_date: datetime


class TmProjectNoteInput(SQLModel):
    note_text: str = Field(min_length=1)


class TmCustomEventCreate(SQLModel):
    event_type: str = Field(min_length=1)
    event_date: date
    reminder_option: str = "none"

    @field_validator("reminder_option")
    @classmethod
    def validate_reminder(cls, value: str) -> str:
        return validate_reminder_option(value)


class TmCustomEventRead(SQLModel):
    id: int
    event_type: str
    event_date: date
    reminder_option: str
    reminder_date: Optional[date] = None
    closure_date: Optional[date] = None
    created_date: datetime


class TmCustomEventClose(SQLModel):
    closure_date: date


def _validate_project_code(value: str) -> str:
    if not re.fullmatch(PROJECT_CODE_PATTERN, value):
        raise ValueError("project_code must be alphanumeric (letters and digits only)")
    return value


def _validate_applicant_type(value: str) -> str:
    if value not in APPLICANT_TYPE_VALUES:
        raise ValueError("applicant_type must be one of MSME, Individual, Company")
    return value


def _validate_tm_type(value: str) -> str:
    if value not in TM_TYPE_VALUES:
        raise ValueError("tm_type must be one of Device/Logo, Wordmark")
    return value


def _validate_tm_usage_status(value: str) -> str:
    if value not in TM_USAGE_STATUS_VALUES:
        raise ValueError("tm_usage_status must be one of 'Proposed to be used', 'Used since'")
    return value


def _validate_selected_classes(values: Optional[List[str]]) -> List[str]:
    cleaned: List[str] = []
    for raw in values or []:
        value = str(raw).strip()
        if value not in SINGLE_CLASS_VALUES:
            raise ValueError(f"tm_selected_classes contains invalid class: {value}")
        cleaned.append(value)
    return cleaned


def _validate_class_description_entries(
    entries: Optional[List[TmClassDescriptionEntry]],
) -> List[TmClassDescriptionEntry]:
    cleaned: List[TmClassDescriptionEntry] = []
    for entry in entries or []:
        class_no = str(entry.class_no).strip()
        if class_no not in SINGLE_CLASS_VALUES:
            raise ValueError(f"application_class_descriptions contains invalid class: {class_no}")
        cleaned.append(TmClassDescriptionEntry(class_no=class_no, description=(entry.description or "").strip()))
    return cleaned


class TmApplicationCreate(SQLModel):
    application_number: str = Field(min_length=7, max_length=7)
    application_date: date
    applicant_name: str = Field(min_length=1)
    applicant_type: str
    tm_name: str = Field(min_length=1)
    tm_type: str
    tm_class: str = Field(min_length=1)
    is_multi_class: bool = False
    tm_usage_status: str
    tm_used_since_date: Optional[date] = None
    tm_selected_classes: List[str] = Field(default_factory=list)
    application_class_descriptions: List[TmClassDescriptionEntry] = Field(default_factory=list)
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    client_docket_no: Optional[str] = None
    applicant_address: str = Field(min_length=1)
    comments: Optional[str] = None

    @field_validator("application_number")
    @classmethod
    def validate_application_number(cls, value: str) -> str:
        if not re.fullmatch(APPLICATION_NUMBER_PATTERN, value):
            raise ValueError("application_number must be exactly 7 digits")
        return value

    @field_validator("applicant_type")
    @classmethod
    def validate_applicant_type(cls, value: str) -> str:
        return _validate_applicant_type(value)

    @field_validator("tm_type")
    @classmethod
    def validate_tm_type(cls, value: str) -> str:
        return _validate_tm_type(value)

    @field_validator("tm_usage_status")
    @classmethod
    def validate_tm_usage_status(cls, value: str) -> str:
        return _validate_tm_usage_status(value)

    @field_validator("tm_class")
    @classmethod
    def validate_tm_class(cls, value: str) -> str:
        return validate_tm_class_value(value)

    @field_validator("tm_selected_classes")
    @classmethod
    def validate_selected_classes(cls, value: Optional[List[str]]) -> List[str]:
        return _validate_selected_classes(value)

    @field_validator("application_class_descriptions")
    @classmethod
    def validate_class_descriptions(
        cls, value: Optional[List[TmClassDescriptionEntry]]
    ) -> List[TmClassDescriptionEntry]:
        return _validate_class_description_entries(value)

    @model_validator(mode="after")
    def validate_class_selection(self) -> "TmApplicationCreate":
        if self.is_multi_class:
            if self.tm_class != MULTI_CLASS_MAIN_VALUE:
                raise ValueError("tm_class must be '99' for a multi class application.")
            if not self.tm_selected_classes:
                raise ValueError("Select at least one class for a multi class application.")
            allowed_classes = set(self.tm_selected_classes)
        else:
            if self.tm_class == MULTI_CLASS_MAIN_VALUE:
                raise ValueError("tm_class must be a specific class (1-45) for a single class application.")
            if self.tm_selected_classes:
                raise ValueError("tm_selected_classes must be empty for a single class application.")
            allowed_classes = {self.tm_class}

        for entry in self.application_class_descriptions:
            if entry.class_no not in allowed_classes:
                raise ValueError(
                    f"application_class_descriptions contains a class ({entry.class_no}) "
                    "that is not part of the selected class(es)."
                )
        return self

    @model_validator(mode="after")
    def validate_usage_details(self) -> "TmApplicationCreate":
        if self.tm_usage_status == "Used since":
            if not self.tm_used_since_date:
                raise ValueError("tm_used_since_date is required when tm_usage_status is 'Used since'.")
            if self.tm_used_since_date > date.today():
                raise ValueError("tm_used_since_date cannot be in the future.")
        elif self.tm_used_since_date is not None:
            raise ValueError("tm_used_since_date must be empty unless tm_usage_status is 'Used since'.")
        return self


class TmApplicationRead(SQLModel):
    id: int
    project_code: str
    application_number: str
    application_date: date
    status_date: date
    applicant_name: str
    applicant_type: Optional[str] = None
    tm_name: str
    tm_type: Optional[str] = None
    tm_class: str
    tm_class_description: Optional[str] = None
    is_multi_class: bool = False
    tm_usage_status: Optional[str] = None
    tm_used_since_date: Optional[date] = None
    tm_selected_classes: List[str] = Field(default_factory=list)
    application_class_descriptions: List[TmClassDescriptionEntry] = Field(default_factory=list)
    applicant_address: str
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    client_docket_no: Optional[str] = None
    client: Optional[PatentClientSummary] = None
    attorney: Optional[PatentAgentSummary] = None
    application_current_status: str
    comments: Optional[str] = None
    filing_date: Optional[date] = None
    fer_followup_due: Optional[date] = None
    hearing_due: Optional[date] = None
    renewal_due: Optional[date] = None
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
    renewal_due: Optional[date] = None
    upcoming_reminders: List[TmReminderRead] = Field(default_factory=list)
    events: List[TmApplicationTimelineEventRead] = Field(default_factory=list)


class TmApplicationUpdate(SQLModel):
    # project_code is system-generated at creation and immutable thereafter -
    # intentionally not accepted here.
    application_number: Optional[str] = None
    application_date: Optional[date] = None
    applicant_name: Optional[str] = None
    applicant_type: Optional[str] = None
    tm_name: Optional[str] = None
    tm_type: Optional[str] = None
    tm_class: Optional[str] = None
    is_multi_class: Optional[bool] = None
    tm_usage_status: Optional[str] = None
    tm_used_since_date: Optional[date] = None
    tm_selected_classes: Optional[List[str]] = None
    application_class_descriptions: Optional[List[TmClassDescriptionEntry]] = None
    client_id: Optional[int] = None
    attorney_id: Optional[int] = None
    client_docket_no: Optional[str] = None
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

    @field_validator("applicant_type")
    @classmethod
    def validate_optional_applicant_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_applicant_type(value)

    @field_validator("tm_type")
    @classmethod
    def validate_optional_tm_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_tm_type(value)

    @field_validator("tm_usage_status")
    @classmethod
    def validate_optional_tm_usage_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_tm_usage_status(value)

    @field_validator("tm_class")
    @classmethod
    def validate_optional_tm_class(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return validate_tm_class_value(value)

    @field_validator("tm_selected_classes")
    @classmethod
    def validate_optional_selected_classes(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return value
        return _validate_selected_classes(value)

    @field_validator("application_class_descriptions")
    @classmethod
    def validate_optional_class_descriptions(
        cls, value: Optional[List[TmClassDescriptionEntry]]
    ) -> Optional[List[TmClassDescriptionEntry]]:
        if value is None:
            return value
        return _validate_class_description_entries(value)

    @model_validator(mode="after")
    def validate_usage_details(self) -> "TmApplicationUpdate":
        # Only enforced when this update touches tm_usage_status - a patch
        # that doesn't mention usage status at all shouldn't be blocked by it.
        if self.tm_usage_status is None:
            return self
        if self.tm_usage_status == "Used since":
            if not self.tm_used_since_date:
                raise ValueError("tm_used_since_date is required when tm_usage_status is 'Used since'.")
            if self.tm_used_since_date > date.today():
                raise ValueError("tm_used_since_date cannot be in the future.")
        elif self.tm_used_since_date is not None:
            raise ValueError("tm_used_since_date must be empty unless tm_usage_status is 'Used since'.")
        return self


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
    applicant_type: Optional[str] = None
    tm_name: str
    tm_type: Optional[str] = None
    tm_class: str
    tm_class_description: Optional[str] = None
    is_multi_class: bool = False
    tm_usage_status: Optional[str] = None
    tm_used_since_date: Optional[date] = None
    tm_selected_classes: List[str] = Field(default_factory=list)
    application_class_descriptions: List[TmClassDescriptionEntry] = Field(default_factory=list)
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
    renewal_due: Optional[date] = None
    upcoming_reminders: List[TmReminderRead] = Field(default_factory=list)
    notes: List[TmProjectNoteRead] = Field(default_factory=list)
    custom_events: List[TmCustomEventRead] = Field(default_factory=list)
    timeline: list[TmProjectTimelineItem]


class TmTimelineStatusUpdate(SQLModel):
    status_id: int = Field(gt=0)
    application_date: date


class TmProjectDetailUpdate(SQLModel):
    application: TmApplicationUpdate
    timeline_updates: list[TmTimelineStatusUpdate] = Field(default_factory=list)
