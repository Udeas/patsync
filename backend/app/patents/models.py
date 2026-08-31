from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel


class PatentProject(SQLModel, table=True):
    __tablename__ = "patent_project"

    id: Optional[int] = Field(default=None, primary_key=True)
    docket_no: str = Field(nullable=False, unique=True, index=True)
    project_mode: str = Field(nullable=False, index=True)
    project_stage: str = Field(default="draft", nullable=False)
    in_application_no: Optional[str] = Field(default=None, unique=True, index=True)
    in_application_date: Optional[date] = Field(default=None)
    applicant_name: str = Field(nullable=False)
    applicant_country: Optional[str] = Field(default=None, max_length=2)
    applicant_address: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    application_title: Optional[str] = Field(default=None)
    attorney_id: Optional[int] = Field(default=None, foreign_key="patent_agent.id")
    client_id: Optional[int] = Field(default=None, foreign_key="patent_client.id")
    client_docket_no: Optional[str] = Field(default=None)
    abandon_reason: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    application_type: Optional[str] = Field(default=None)
    provisional_kind: Optional[str] = Field(default=None, max_length=3)
    parent_project_id: Optional[int] = Field(default=None, foreign_key="patent_project.id")
    parent_application_no: Optional[str] = Field(default=None)
    parent_application_date: Optional[date] = Field(default=None)
    grant_number: Optional[str] = Field(default=None)
    annuity_paid_upto: Optional[date] = Field(default=None)
    next_annuity_due: Optional[date] = Field(default=None)
    annuity_transferred_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    annuity_transferred_comment: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    pct_wipo_filed_only: bool = Field(default=False)
    is_archived: bool = Field(default=False, nullable=False, index=True)
    created_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    modified_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class PatentInventor(SQLModel, table=True):
    __tablename__ = "patent_inventor"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(nullable=False, foreign_key="patent_project.id", index=True)
    name: str = Field(nullable=False)
    nationality: Optional[str] = Field(default=None, max_length=2)
    address: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))


class PatentApplicant(SQLModel, table=True):
    __tablename__ = "patent_applicant"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(nullable=False, foreign_key="patent_project.id", index=True)
    name: str = Field(nullable=False)
    country: Optional[str] = Field(default=None, max_length=2)
    address: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))


class PatentInternationalApplication(SQLModel, table=True):
    __tablename__ = "patent_international_application"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(nullable=False, foreign_key="patent_project.id", index=True)
    international_application_no: str = Field(nullable=False)
    international_application_date: date = Field(nullable=False)


class PatentPriority(SQLModel, table=True):
    __tablename__ = "patent_priority"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(nullable=False, foreign_key="patent_project.id", index=True)
    priority_application_no: str = Field(nullable=False)
    priority_application_date: date = Field(nullable=False)
    country: str = Field(nullable=False, max_length=2)
    title: str = Field(nullable=False)


class PatentStatusEvent(SQLModel, table=True):
    __tablename__ = "patent_status_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(nullable=False, foreign_key="patent_project.id", index=True)
    status_id: int = Field(nullable=False)
    status_date: date = Field(nullable=False)


class PatentAnnuityPayment(SQLModel, table=True):
    __tablename__ = "patent_annuity_payment"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(nullable=False, foreign_key="patent_project.id", index=True)
    payment_date: date = Field(nullable=False)
    total_fee: int = Field(nullable=False)
    created_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class PatentAnnuityPaymentYear(SQLModel, table=True):
    __tablename__ = "patent_annuity_payment_year"

    id: Optional[int] = Field(default=None, primary_key=True)
    payment_id: int = Field(nullable=False, foreign_key="patent_annuity_payment.id", index=True)
    renewal_year: int = Field(nullable=False)


class PatentProjectNote(SQLModel, table=True):
    __tablename__ = "patent_project_note"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(nullable=False, foreign_key="patent_project.id", index=True)
    note_text: str = Field(sa_column=Column(Text, nullable=False))
    created_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class PatentClient(SQLModel, table=True):
    __tablename__ = "patent_client"

    id: Optional[int] = Field(default=None, primary_key=True)
    client_code: str = Field(nullable=False, unique=True, max_length=10, index=True)
    name: str = Field(nullable=False, index=True)
    address: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    email: Optional[str] = Field(default=None)
    key_contacts: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    docketing_email: Optional[str] = Field(default=None)
    client_types: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))


class PatentAgent(SQLModel, table=True):
    __tablename__ = "patent_agent"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    agent_code: str = Field(nullable=False, unique=True, index=True)
    address: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    mobile_1: str = Field(nullable=False)
    mobile_2: Optional[str] = Field(default=None)
    email_1: str = Field(nullable=False)
    email_2: Optional[str] = Field(default=None)
