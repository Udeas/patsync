from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel

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


class PatentClientRead(SQLModel):
    id: int
    client_code: str
    name: str
    address: Optional[str] = None
    email: Optional[str] = None
    key_contacts: list[str] = Field(default_factory=list)
    docketing_email: Optional[str] = None


class PatentClientUpdate(SQLModel):
    client_code: str = Field(min_length=1, max_length=10)
    name: str
    address: Optional[str] = None
    email: Optional[str] = None
    key_contacts: list[str] = Field(default_factory=list)
    docketing_email: Optional[str] = None
