from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.domain.custom_events import validate_reminder_option
from .validators import parse_in_application_number, validate_pct_international_number


class PatentInventorInput(SQLModel):
    name: str
    nationality: Optional[str] = Field(default=None, max_length=2)
    address: Optional[str] = None


class PatentApplicantInput(SQLModel):
    name: str
    country: Optional[str] = Field(default=None, max_length=2)
    address: Optional[str] = None


class PatentPriorityInput(SQLModel):
    priority_application_no: str
    priority_application_date: date
    country: str = Field(max_length=2)
    title: str


class PatentInternationalInput(SQLModel):
    international_application_no: str
    international_application_date: date

    @field_validator("international_application_no")
    @classmethod
    def validate_international_no(cls, value: str) -> str:
        return validate_pct_international_number(value)


class PatentInventorRead(SQLModel):
    name: str
    nationality: Optional[str] = None
    address: Optional[str] = None


class PatentApplicantRead(SQLModel):
    name: str
    country: Optional[str] = None
    address: Optional[str] = None


class PatentPriorityRead(SQLModel):
    priority_application_no: str
    priority_application_date: date
    country: str
    title: str


class PatentInternationalRead(SQLModel):
    international_application_no: str
    international_application_date: date


class PatentStatusEventRead(SQLModel):
    status_id: int
    status_date: date


class PatentProjectNoteRead(SQLModel):
    id: int
    note_text: str
    created_date: datetime


class PatentCustomEventReminderRead(SQLModel):
    kind: str
    fire_on: date
    label: str


class PatentCustomEventRead(SQLModel):
    id: int
    event_type: str
    event_date: date
    reminder_option: str
    reminder_date: Optional[date] = None
    closure_date: Optional[date] = None
    created_date: datetime


class PatentCustomEventCreate(SQLModel):
    event_type: str = Field(min_length=1)
    event_date: date
    reminder_option: str = "none"

    @field_validator("reminder_option")
    @classmethod
    def validate_reminder(cls, value: str) -> str:
        return validate_reminder_option(value)


class PatentCustomEventClose(SQLModel):
    closure_date: date


class PatentAgentSummary(SQLModel):
    id: int
    name: str
    agent_code: str
    address: Optional[str] = None
    mobile_1: str
    mobile_2: Optional[str] = None
    email_1: str
    email_2: Optional[str] = None


class PatentClientSummary(SQLModel):
    id: int
    client_code: str
    name: str


class PatentProjectCreate(SQLModel):
    project_mode: Literal["draft", "final"]
    application_type: str
    docket_no: str
    in_application_no: Optional[str] = None
    in_application_date: Optional[date] = None
    applicant_name: str
    applicant_country: Optional[str] = Field(default=None, max_length=2)
    applicant_address: Optional[str] = None
    applicants: list[PatentApplicantInput] = Field(default_factory=list)
    application_title: Optional[str] = None
    attorney_id: Optional[int] = None
    client_id: Optional[int] = None
    client_docket_no: Optional[str] = None
    provisional_kind: Optional[Literal["OP", "ONP"]] = None
    pct_wipo_filed_only: bool = False
    international_application_no: Optional[str] = None
    international_application_date: Optional[date] = None
    parent_project_id: Optional[int] = None
    parent_application_no: Optional[str] = None
    parent_application_date: Optional[date] = None
    grant_number: Optional[str] = None
    annuity_paid_upto: Optional[date] = None
    next_annuity_due: Optional[date] = None
    inventors: list[PatentInventorInput] = Field(default_factory=list)
    priorities: list[PatentPriorityInput] = Field(default_factory=list)
    international_applications: list[PatentInternationalInput] = Field(default_factory=list)

    @field_validator("in_application_no")
    @classmethod
    def validate_in_application_no(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        parse_in_application_number(value)
        return value

    @field_validator("international_application_no")
    @classmethod
    def validate_international_application_no(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return validate_pct_international_number(value)


class PatentProjectRead(SQLModel):
    id: int
    project_mode: str
    project_stage: str
    docket_no: str
    in_application_no: Optional[str] = None
    in_application_date: Optional[date] = None
    applicant_name: str
    applicant_country: Optional[str] = None
    applicant_address: Optional[str] = None
    applicants: list[PatentApplicantRead] = Field(default_factory=list)
    application_title: Optional[str] = None
    application_type: Optional[str] = None
    provisional_kind: Optional[str] = None
    pct_wipo_filed_only: bool = False
    parent_project_id: Optional[int] = None
    parent_application_no: Optional[str] = None
    parent_application_date: Optional[date] = None
    parent_docket_no: Optional[str] = None
    parent_client_docket_no: Optional[str] = None
    parent_priority_dates: list[date] = Field(default_factory=list)
    grant_number: Optional[str] = None
    annuity_paid_upto: Optional[date] = None
    next_annuity_due: Optional[date] = None
    is_annuity_transferred: bool = False
    current_status_id: Optional[int] = None
    current_status_date: Optional[date] = None
    due_action: Optional[str] = None
    action_due_date: Optional[date] = None
    inventors: list[PatentInventorRead] = Field(default_factory=list)
    priorities: Optional[list[PatentPriorityRead]] = Field(default_factory=list)
    international_applications: list[PatentInternationalRead] = Field(default_factory=list)
    status_events: list[PatentStatusEventRead] = Field(default_factory=list)
    attorney: Optional[PatentAgentSummary] = None
    client: Optional[PatentClientSummary] = None
    client_docket_no: Optional[str] = None
    abandon_reason: Optional[str] = None
    is_archived: bool = False
    notes: list[PatentProjectNoteRead] = Field(default_factory=list)
    custom_events: list[PatentCustomEventRead] = Field(default_factory=list)
    custom_event_reminders: list[PatentCustomEventReminderRead] = Field(default_factory=list)


class PatentDraftFinalizeRequest(SQLModel):
    in_application_no: str
    in_application_date: date

    @field_validator("in_application_no")
    @classmethod
    def validate_final_in_application_no(cls, value: str) -> str:
        parse_in_application_number(value)
        return value


class PatentStatusUpdate(SQLModel):
    status_id: int = Field(gt=0)
    status_date: date
    abandon_reason: Optional[str] = None


class PatentProjectUpdate(SQLModel):
    docket_no: str
    project_mode: Optional[Literal["draft", "final"]] = None
    application_type: Optional[str] = None
    client_docket_no: Optional[str] = None
    application_title: Optional[str] = None
    in_application_no: Optional[str] = None
    in_application_date: Optional[date] = None
    applicant_name: str
    applicant_country: Optional[str] = Field(default=None, max_length=2)
    applicant_address: Optional[str] = None
    applicants: Optional[list[PatentApplicantInput]] = None
    attorney_id: Optional[int] = None
    client_id: Optional[int] = None
    provisional_kind: Optional[Literal["OP", "ONP"]] = None
    pct_wipo_filed_only: Optional[bool] = None
    parent_project_id: Optional[int] = None
    parent_application_no: Optional[str] = None
    parent_application_date: Optional[date] = None
    grant_number: Optional[str] = None
    annuity_paid_upto: Optional[date] = None
    next_annuity_due: Optional[date] = None
    inventors: Optional[list[PatentInventorInput]] = None
    priorities: Optional[list[PatentPriorityInput]] = None
    international_applications: Optional[list[PatentInternationalInput]] = None

    @field_validator("in_application_no")
    @classmethod
    def validate_update_in_application_no(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        parse_in_application_number(value)
        return value


class PatentTimelineStatusUpdate(SQLModel):
    status_id: int = Field(gt=0)
    status_date: date


class PatentProjectDetailUpdate(SQLModel):
    application: PatentProjectUpdate
    timeline_updates: list[PatentTimelineStatusUpdate] = Field(default_factory=list)


class PatentAgentInput(SQLModel):
    name: str
    agent_code: str
    address: Optional[str] = None
    mobile_1: str
    mobile_2: Optional[str] = None
    email_1: str
    email_2: Optional[str] = None


class PatentAgentRead(PatentAgentInput):
    id: int


class PatentAgentUpdate(SQLModel):
    name: str
    agent_code: str
    address: Optional[str] = None
    mobile_1: str
    mobile_2: Optional[str] = None
    email_1: str
    email_2: Optional[str] = None


class PatentClientInput(SQLModel):
    client_code: str = Field(min_length=1, max_length=10)
    name: str
    address: Optional[str] = None
    email: Optional[str] = None
    key_contacts: list[str] = Field(default_factory=list)
    docketing_email: Optional[str] = None
    client_types: list[str] = Field(default_factory=list)


class PatentClientRead(SQLModel):
    id: int
    client_code: str
    name: str
    address: Optional[str] = None
    email: Optional[str] = None
    key_contacts: list[str] = Field(default_factory=list)
    docketing_email: Optional[str] = None
    client_types: list[str] = Field(default_factory=list)


class PatentClientUpdate(SQLModel):
    client_code: str = Field(min_length=1, max_length=10)
    name: str
    address: Optional[str] = None
    email: Optional[str] = None
    key_contacts: list[str] = Field(default_factory=list)
    docketing_email: Optional[str] = None
    client_types: list[str] = Field(default_factory=list)


class PatentAnnuityPaymentInput(SQLModel):
    payment_date: date
    years: list[int] = Field(min_length=1)


class PatentAnnuityPaymentRead(SQLModel):
    id: int
    payment_date: date
    total_fee: int
    years: list[int] = Field(default_factory=list)
    years_label: str = ""


class PatentAnnuityScheduleRow(SQLModel):
    year: int
    due_date: date
    fee: int
    status: Literal["paid", "unpaid"]
    payment_id: Optional[int] = None


class PatentAnnuitySummary(SQLModel):
    filing_date: Optional[date] = None
    grant_date: Optional[date] = None
    fee_category: str = "standard"
    schedule: list[PatentAnnuityScheduleRow] = Field(default_factory=list)
    payments: list[PatentAnnuityPaymentRead] = Field(default_factory=list)
    paid_years: list[int] = Field(default_factory=list)
    paid_till_year: Optional[int] = None
    paid_till_date: Optional[date] = None
    next_due_year: Optional[int] = None
    next_due_date: Optional[date] = None
    is_post_grant_deadline_pending: bool = False
    accumulated_unpaid_years: list[int] = Field(default_factory=list)
    orphaned_paid_years: list[int] = Field(default_factory=list)
    is_transferred: bool = False
    transferred_at: Optional[datetime] = None
    transferred_comment: Optional[str] = None


class PatentAnnuityTransferInput(SQLModel):
    comment: str = Field(min_length=1)


class PatentProjectNoteInput(SQLModel):
    note_text: str = Field(min_length=1)
