from enum import Enum
from typing import Optional
from datetime import date, datetime
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text, DateTime


class ApplicationStatus(str, Enum):
    APPLICATION_FILED = "Application Filed"
    SECRECY_DIRECTIONS = "Secrecy Directions"
    ABANDONED = "Abandoned"
    FER_ISSUED = "FER Issued"
    FER_RESPONSE_SUBMITTED = "FER Response Submitted"
    CASE_UNDER_HEARING = "Case under Hearing"
    GRANTED = "Granted"
    ACCEPTED_AND_PUBLISHED = "Accepted and Published"


class Application(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    application_number: str = Field(unique=True, nullable=False)
    application_date: date
    applicant_name: str
    applicant_address: str = Field(sa_column=Column(Text))
    application_title: str
    application_current_status: ApplicationStatus
    hearing_date: Optional[date] = None
    grant_no: Optional[str] = None
    grant_date: Optional[date] = None
    certificate_status: str
    renewal_due_date: date
    examination_response_due_date: date
    comments: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=True)))
    updated_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=True)))