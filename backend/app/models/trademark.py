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
    tm_name: str = Field(nullable=False)
    tm_class: str = Field(nullable=False)
    client_id: Optional[int] = Field(default=None, foreign_key="patent_client.id")
    attorney_id: Optional[int] = Field(default=None, foreign_key="patent_agent.id")
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
