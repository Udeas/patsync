from collections import defaultdict
from datetime import date, datetime
from typing import DefaultDict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, desc, select

from app.domain.patent_timeline import build_timeline_for_application
from app.models.applications import ApplicationData, ApplicationState, Status
from app.schemas.applications import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationTimelineEventRead,
    ApplicationTimelineRead,
    ApplicationUpdate,
    ReminderRead,
    StatusRead,
)
from app.status_catalog import STATUS_ID_APPLICATION_FILED


def _utcnow() -> datetime:
    return datetime.utcnow()


def _states_ordered_for_app(session: Session, application_num: str) -> List[Tuple[int, date, str]]:
    rows = session.exec(
        select(ApplicationState, Status)
        .join(Status)
        .where(ApplicationState.application_num == application_num)
        .order_by(ApplicationState.id)
    ).all()
    return [(state.id or 0, state.application_date, st.status) for state, st in rows]


def _states_grouped(
    session: Session,
    application_nums: List[str],
) -> dict[str, List[Tuple[int, date, str]]]:
    nums = [n for n in application_nums if n]
    if not nums:
        return {}
    rows = session.exec(
        select(ApplicationState, Status)
        .join(Status)
        .where(ApplicationState.application_num.in_(nums))
        .order_by(ApplicationState.application_num, ApplicationState.id)
    ).all()
    grouped: DefaultDict[str, List[Tuple[int, date, str]]] = defaultdict(list)
    for state, st in rows:
        grouped[state.application_num].append((state.id or 0, state.application_date, st.status))
    return dict(grouped)


def _read_model_with_timeline(
    data: ApplicationData,
    state: ApplicationState,
    status: Status,
    states_ordered: List[Tuple[int, date, str]],
    today: date,
) -> ApplicationRead:
    tl = build_timeline_for_application(
        states_ordered=states_ordered,
        current_status_name=status.status,
        today=today,
    )
    reminders = [
        ReminderRead(kind=r.kind, fire_on=r.fire_on, label=r.label) for r in tl.upcoming_reminders
    ]
    return ApplicationRead(
        id=data.id or 0,
        application_number=data.application_num,
        application_date=state.application_date,
        applicant_name=data.applicant_name,
        applicant_address=data.applicant_address,
        application_title=data.application_title,
        application_current_status=status.status,
        comments=data.comments,
        filing_date=tl.filing_date,
        fer_response_deadline=tl.fer_response_deadline,
        upcoming_reminders=reminders,
    )


def list_statuses(session: Session) -> List[StatusRead]:
    rows = session.exec(select(Status).order_by(Status.id)).all()
    return [StatusRead(id=row.id or 0, status=row.status) for row in rows]


def create_application(session: Session, application: ApplicationCreate) -> ApplicationRead:
    status_row = session.get(Status, STATUS_ID_APPLICATION_FILED)
    if not status_row:
        raise ValueError("status table must contain Application Filed before creating applications")

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
            status_id=STATUS_ID_APPLICATION_FILED,
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

    today = date.today()
    states = [(db_state.id or 0, db_state.application_date, status_row.status)]
    return _read_model_with_timeline(db_application, db_state, status_row, states, today)


def get_applications(session: Session) -> List[ApplicationRead]:
    latest_state_subquery = (
        select(
            ApplicationState.application_num.label("application_num"),
            func.max(ApplicationState.id).label("latest_state_id"),
        )
        .group_by(ApplicationState.application_num)
        .subquery()
    )

    query = (
        select(ApplicationData, ApplicationState, Status)
        .join(
            latest_state_subquery,
            latest_state_subquery.c.application_num == ApplicationData.application_num,
        )
        .join(ApplicationState, ApplicationState.id == latest_state_subquery.c.latest_state_id)
        .join(Status, Status.id == ApplicationState.status_id)
        .order_by(desc(ApplicationState.application_date), desc(ApplicationState.id))
    )
    rows = session.exec(query).all()
    today = date.today()
    nums = [data.application_num for data, _state, _status in rows]
    grouped = _states_grouped(session, nums)
    return [
        _read_model_with_timeline(data, state, status, grouped.get(data.application_num, []), today)
        for data, state, status in rows
    ]


def get_application_by_id(session: Session, application_id: int) -> Optional[ApplicationRead]:
    latest_state_subquery = (
        select(
            ApplicationState.application_num.label("application_num"),
            func.max(ApplicationState.id).label("latest_state_id"),
        )
        .group_by(ApplicationState.application_num)
        .subquery()
    )

    query = (
        select(ApplicationData, ApplicationState, Status)
        .join(
            latest_state_subquery,
            latest_state_subquery.c.application_num == ApplicationData.application_num,
        )
        .join(ApplicationState, ApplicationState.id == latest_state_subquery.c.latest_state_id)
        .join(Status, Status.id == ApplicationState.status_id)
        .where(ApplicationData.id == application_id)
    )
    row = session.exec(query).first()
    if not row:
        return None
    data, state, status = row
    today = date.today()
    states = _states_ordered_for_app(session, data.application_num)
    return _read_model_with_timeline(data, state, status, states, today)


def get_application_timeline(session: Session, application_id: int) -> Optional[ApplicationTimelineRead]:
    db_application = session.get(ApplicationData, application_id)
    if not db_application:
        return None
    states = _states_ordered_for_app(session, db_application.application_num)
    current_status = states[-1][2] if states else ""

    today = date.today()
    tl = build_timeline_for_application(
        states_ordered=states,
        current_status_name=current_status,
        today=today,
    )

    reminders = [
        ReminderRead(kind=r.kind, fire_on=r.fire_on, label=r.label) for r in tl.upcoming_reminders
    ]

    raw_states = session.exec(
        select(ApplicationState, Status)
        .join(Status)
        .where(ApplicationState.application_num == db_application.application_num)
        .order_by(ApplicationState.id)
    ).all()
    events = [
        ApplicationTimelineEventRead(
            state_id=st.id or 0,
            status=meta.status,
            application_date=st.application_date,
        )
        for st, meta in raw_states
    ]

    return ApplicationTimelineRead(
        application_number=db_application.application_num,
        filing_date=tl.filing_date,
        fer_response_deadline=tl.fer_response_deadline,
        upcoming_reminders=reminders,
        events=events,
    )


def update_application(session: Session, application_id: int, update_data: ApplicationUpdate) -> Optional[ApplicationRead]:
    db_application = session.get(ApplicationData, application_id)
    if not db_application:
        return None

    old_number = db_application.application_num
    db_state = session.exec(
        select(ApplicationState)
        .where(ApplicationState.application_num == old_number)
        .order_by(desc(ApplicationState.id))
    ).first()
    if not db_state:
        return None

    now = _utcnow()
    update_dict = update_data.model_dump(exclude_unset=True)

    new_number = update_dict.get("application_number", old_number)
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

    states_to_update: List[ApplicationState] = [db_state]
    if "application_number" in update_dict and new_number != old_number:
        all_states = session.exec(
            select(ApplicationState).where(ApplicationState.application_num == old_number)
        ).all()
        for state in all_states:
            state.application_num = new_number
            state.modified_date = now
        states_to_update = all_states

    filed_rows: List[ApplicationState] = []

    if "application_date" in update_dict:
        new_date_val = update_dict["application_date"]
        filed_rows = session.exec(
            select(ApplicationState)
            .where(
                ApplicationState.application_num == db_application.application_num,
                ApplicationState.status_id == STATUS_ID_APPLICATION_FILED,
            )
            .order_by(ApplicationState.id)
        ).all()
        if filed_rows:
            for fr in filed_rows:
                fr.application_date = new_date_val
                fr.modified_date = now
        else:
            db_state.application_date = new_date_val
            db_state.modified_date = now
    else:
        db_state.modified_date = now

    to_add: set[ApplicationState] = set(states_to_update)
    to_add.update(filed_rows)

    try:
        session.add(db_application)
        for state in to_add:
            session.add(state)
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

    now = _utcnow()
    db_state = session.exec(
        select(ApplicationState)
        .where(
            ApplicationState.application_num == db_application.application_num,
            ApplicationState.status_id == status_update.status_id,
        )
        .order_by(desc(ApplicationState.id))
    ).first()

    if db_state:
        db_state.application_date = status_update.application_date
        db_state.modified_date = now
    else:
        db_state = ApplicationState(
            application_num=db_application.application_num,
            status_id=status_update.status_id,
            application_date=status_update.application_date,
            created_date=now,
            modified_date=now,
        )
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