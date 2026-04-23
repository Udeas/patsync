from datetime import datetime
from typing import Optional, List
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select, desc
from ..models.applications import ApplicationData, ApplicationState, Status
from ..schemas.applications import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    ApplicationStatusUpdate,
    StatusRead,
)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _to_read_model(data: ApplicationData, state: ApplicationState, status: Status) -> ApplicationRead:
    return ApplicationRead(
        id=data.id or 0,
        application_number=data.application_num,
        application_date=state.application_date,
        applicant_name=data.applicant_name,
        applicant_address=data.applicant_address,
        application_title=data.application_title,
        application_current_status=status.status,
        comments=data.comments,
    )


def list_statuses(session: Session) -> List[StatusRead]:
    rows = session.exec(select(Status).order_by(Status.id)).all()
    return [StatusRead(id=row.id or 0, status=row.status) for row in rows]


def create_application(session: Session, application: ApplicationCreate) -> ApplicationRead:
    status_row = session.get(Status, 1)
    if not status_row:
        raise ValueError("status table must contain id=1 before creating applications")

    now = _utcnow()
    db_application = ApplicationData(
        application_num=application.application_number,
        applicant_name=application.applicant_name,
        applicant_address=application.applicant_address,
        application_title=application.application_title,
        comments=application.comments,
        created_date=now,
        modified_date=now,
    )

    try:
        session.add(db_application)
        session.flush()

        db_state = ApplicationState(
            application_num=application.application_number,
            status_id=1,
            application_date=application.application_date,
            created_date=now,
            modified_date=now,
        )
        session.add(db_state)
        session.commit()
        session.refresh(db_application)
        session.refresh(db_state)
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("application_number already exists or violates constraints") from exc

    return _to_read_model(db_application, db_state, status_row)


def get_applications(session: Session) -> List[ApplicationRead]:
    query = (
        select(ApplicationData, ApplicationState, Status)
        .join(ApplicationState, ApplicationState.application_num == ApplicationData.application_num)
        .join(Status, Status.id == ApplicationState.status_id)
        .order_by(desc(ApplicationState.application_date), desc(ApplicationState.id))
    )
    rows = session.exec(query).all()
    return [_to_read_model(data, state, status) for data, state, status in rows]


def get_application_by_id(session: Session, application_id: int) -> Optional[ApplicationRead]:
    query = (
        select(ApplicationData, ApplicationState, Status)
        .join(ApplicationState, ApplicationState.application_num == ApplicationData.application_num)
        .join(Status, Status.id == ApplicationState.status_id)
        .where(ApplicationData.id == application_id)
        .order_by(desc(ApplicationState.id))
    )
    row = session.exec(query).first()
    if not row:
        return None
    data, state, status = row
    return _to_read_model(data, state, status)


def update_application(session: Session, application_id: int, update_data: ApplicationUpdate) -> Optional[ApplicationRead]:
    db_application = session.get(ApplicationData, application_id)
    if not db_application:
        return None

    db_state = session.exec(
        select(ApplicationState)
        .where(ApplicationState.application_num == db_application.application_num)
        .order_by(desc(ApplicationState.id))
    ).first()
    if not db_state:
        return None

    now = _utcnow()
    update_dict = update_data.model_dump(exclude_unset=True)

    new_number = update_dict.get("application_number", db_application.application_num)
    if "application_number" in update_dict:
        db_application.application_num = new_number

    if "applicant_name" in update_dict:
        db_application.applicant_name = update_dict["applicant_name"]
    if "applicant_address" in update_dict:
        db_application.applicant_address = update_dict["applicant_address"]
    if "application_title" in update_dict:
        db_application.application_title = update_dict["application_title"]
    if "comments" in update_dict:
        db_application.comments = update_dict["comments"]
    db_application.modified_date = now

    if "application_number" in update_dict:
        db_state.application_num = new_number
    if "application_date" in update_dict:
        db_state.application_date = update_dict["application_date"]
    db_state.modified_date = now

    try:
        session.add(db_application)
        session.add(db_state)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("application_number already exists or violates constraints") from exc

    return get_application_by_id(session, application_id)


def update_application_status(
    session: Session, application_id: int, status_update: ApplicationStatusUpdate
) -> Optional[ApplicationRead]:
    db_application = session.get(ApplicationData, application_id)
    if not db_application:
        return None

    status_row = session.get(Status, status_update.status_id)
    if not status_row:
        raise ValueError("invalid status_id")

    db_state = session.exec(
        select(ApplicationState)
        .where(ApplicationState.application_num == db_application.application_num)
        .order_by(desc(ApplicationState.id))
    ).first()
    if not db_state:
        return None

    db_state.status_id = status_update.status_id
    db_state.modified_date = _utcnow()
    session.add(db_state)
    session.commit()
    return get_application_by_id(session, application_id)


def delete_application(session: Session, application_id: int) -> bool:
    db_application = session.get(ApplicationData, application_id)
    if not db_application:
        return False

    session.delete(db_application)
    session.commit()
    return True
