from datetime import date, datetime
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text, DateTime


class ApplicationData(SQLModel, table=True):
    __tablename__ = "application_data"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_num: str = Field(nullable=False, unique=True, index=True)
    applicant_name: str = Field(nullable=False)
    application_title: str = Field(nullable=False)
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


class Status(SQLModel, table=True):
    __tablename__ = "status"

    id: Optional[int] = Field(default=None, primary_key=True)
    status: str = Field(nullable=False, unique=True)


class ApplicationState(SQLModel, table=True):
    __tablename__ = "application_state"

    id: Optional[int] = Field(default=None, primary_key=True)
    application_num: str = Field(
        nullable=False,
        foreign_key="application_data.application_num",
        index=True,
    )
    status_id: int = Field(nullable=False, foreign_key="status.id")
    application_date: date = Field(nullable=False)
    created_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    modified_date: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
