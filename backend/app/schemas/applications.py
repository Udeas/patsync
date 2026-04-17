from typing import Optional
from datetime import date, datetime
from uuid import UUID
from sqlmodel import SQLModel
from ..models.applications import ApplicationStatus


class ApplicationCreate(SQLModel):
    application_number: str
    application_date: date
    applicant_name: str
    applicant_address: str
    application_title: str
    application_current_status: ApplicationStatus
    hearing_date: Optional[date] = None
    grant_no: Optional[str] = None
    grant_date: Optional[date] = None
    certificate_status: str
    renewal_due_date: date
    examination_response_due_date: date
    comments: str


class ApplicationRead(SQLModel):
    id: UUID
    application_number: str
    application_date: date
    applicant_name: str
    applicant_address: str
    application_title: str
    application_current_status: ApplicationStatus
    hearing_date: Optional[date] = None
    grant_no: Optional[str] = None
    grant_date: Optional[date] = None
    certificate_status: str
    renewal_due_date: date
    examination_response_due_date: date
    comments: str
    created_at: datetime
    updated_at: datetime


class ApplicationUpdate(SQLModel):
    application_number: Optional[str] = None
    application_date: Optional[date] = None
    applicant_name: Optional[str] = None
    applicant_address: Optional[str] = None
    application_title: Optional[str] = None
    application_current_status: Optional[ApplicationStatus] = None
    hearing_date: Optional[date] = None
    grant_no: Optional[str] = None
    grant_date: Optional[date] = None
    certificate_status: Optional[str] = None
    renewal_due_date: Optional[date] = None
    examination_response_due_date: Optional[date] = None
    comments: Optional[str] = None