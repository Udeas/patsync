from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel


class TmApplicationData(SQLModel, table=True):
    __tablename__ = "tm_application_data"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_code: str = Field(nullable=False, unique=True, index=True)
    application_num: str = Field(nullable=False, unique=True, index=True)
    applicant_name: str = Field(nullable=False)
    applicant_type: Optional[str] = Field(default=None)
    tm_name: str = Field(nullable=False)
    tm_type: Optional[str] = Field(default=None)
    tm_class: str = Field(nullable=False)
    is_multi_class: bool = Field(default=False)
    tm_usage_status: Optional[str] = Field(default=None)
    tm_used_since_date: Optional[date] = Field(default=None)
    tm_selected_classes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    application_class_description: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    client_id: Optional[int] = Field(default=None, foreign_key="patent_client.id")
    attorney_id: Optional[int] = Field(default=None, foreign_key="patent_agent.id")
    client_docket_no: Optional[str] = Field(default=None)
    applicant_address: str = Field(sa_column=Column(Text, nullable=False))
    comments: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    modified_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_status_updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class TmProjectNote(SQLModel, table=True):
    __tablename__ = "tm_project_note"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(nullable=False, foreign_key="tm_application_data.id", index=True)
    note_text: str = Field(sa_column=Column(Text, nullable=False))
    created_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class TmCustomEvent(SQLModel, table=True):
    __tablename__ = "tm_custom_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(nullable=False, foreign_key="tm_application_data.id", index=True)
    event_type: str = Field(nullable=False)
    event_date: date = Field(nullable=False)
    reminder_option: str = Field(nullable=False)
    reminder_date: Optional[date] = Field(default=None)
    closure_date: Optional[date] = Field(default=None)
    created_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class TmStatus(SQLModel, table=True):
    __tablename__ = "tm_status"

    id: Optional[int] = Field(default=None, primary_key=True)
    status: str = Field(nullable=False, unique=True)


class TmApplicationState(SQLModel, table=True):
    __tablename__ = "tm_application_state"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_num: str = Field(
        nullable=False,
        foreign_key="tm_application_data.application_num",
        index=True,
    )
    status_id: int = Field(nullable=False, foreign_key="tm_status.id")
    application_date: date = Field(nullable=False)
    created_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    modified_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
