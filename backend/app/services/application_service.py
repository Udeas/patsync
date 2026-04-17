from sqlmodel import Session, select
from datetime import datetime
from typing import Optional, List
from uuid import UUID
from ..models.applications import Application
from ..schemas.applications import ApplicationCreate, ApplicationRead, ApplicationUpdate


def create_application(session: Session, application: ApplicationCreate) -> ApplicationRead:
    db_application = Application.from_orm(application)
    session.add(db_application)
    session.commit()
    session.refresh(db_application)
    return ApplicationRead.from_orm(db_application)


def get_applications(session: Session) -> List[ApplicationRead]:
    applications = session.exec(select(Application)).all()
    return [ApplicationRead.from_orm(app) for app in applications]


def get_application_by_id(session: Session, application_id: UUID) -> Optional[ApplicationRead]:
    application = session.get(Application, application_id)
    if application:
        return ApplicationRead.from_orm(application)
    return None


def update_application(session: Session, application_id: UUID, update_data: ApplicationUpdate) -> Optional[ApplicationRead]:
    application = session.get(Application, application_id)
    if not application:
        return None
    update_dict = update_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(application, key, value)
    application.updated_at = datetime.utcnow()
    session.add(application)
    session.commit()
    session.refresh(application)
    return ApplicationRead.from_orm(application)


def delete_application(session: Session, application_id: UUID) -> bool:
    application = session.get(Application, application_id)
    if not application:
        return False
    session.delete(application)
    session.commit()
    return True