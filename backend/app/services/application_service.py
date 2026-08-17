from collections import defaultdict
from datetime import date, datetime
from typing import DefaultDict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, desc, select

from app.domain.patent_timeline import build_timeline_for_application
from app.domain.status_workflow import (
    enabled_status_ids,
    is_optional_status,
    validate_status_change,
    validate_timeline_updates,
)
from app.models.applications import ApplicationData, ApplicationState, Status
from app.patents.models import PatentAgent, PatentClient
from app.schemas.applications import (
    ApplicationCreate,
    ProjectDetailRead,
    ProjectDetailUpdate,
    ProjectTimelineItem,
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


def _touch_last_status_updated(db_application: ApplicationData, when: Optional[datetime] = None) -> None:
    ts = when or _utcnow()
    db_application.last_status_updated_at = ts
    db_application.modified_date = ts


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


def _client_summary(client: PatentClient) -> dict:
    return {"id": client.id, "client_code": client.client_code, "name": client.name}


def _attorney_summary(agent: PatentAgent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "agent_code": agent.agent_code,
        "address": agent.address,
        "mobile_1": agent.mobile_1,
        "mobile_2": agent.mobile_2,
        "email_1": agent.email_1,
        "email_2": agent.email_2,
    }


def _resolve_client_summary(session, client_id, clients_by_id):
    if not client_id:
        return None
    if clients_by_id is not None:
        return clients_by_id.get(client_id)
    client = session.get(PatentClient, client_id)
    return _client_summary(client) if client else None


def _resolve_attorney_summary(session, attorney_id, agents_by_id):
    if not attorney_id:
        return None
    if agents_by_id is not None:
        return agents_by_id.get(attorney_id)
    agent = session.get(PatentAgent, attorney_id)
    return _attorney_summary(agent) if agent else None


def _load_contacts_bulk(session: Session, datas) -> tuple[dict[int, dict], dict[int, dict]]:
    """Batch-load client + attorney summaries for many rows (no per-row N+1)."""
    client_ids = {d.client_id for d in datas if d.client_id}
    attorney_ids = {d.attorney_id for d in datas if d.attorney_id}
    clients_by_id: dict[int, dict] = {}
    if client_ids:
        for client in session.exec(
            select(PatentClient).where(PatentClient.id.in_(client_ids))
        ).all():
            clients_by_id[client.id] = _client_summary(client)
    agents_by_id: dict[int, dict] = {}
    if attorney_ids:
        for agent in session.exec(
            select(PatentAgent).where(PatentAgent.id.in_(attorney_ids))
        ).all():
            agents_by_id[agent.id] = _attorney_summary(agent)
    return clients_by_id, agents_by_id


def _read_model_with_timeline(
    session: Session,
    data: ApplicationData,
    state: ApplicationState,
    status: Status,
    states_ordered: List[Tuple[int, date, str]],
    today: date,
    clients_by_id: dict[int, dict] | None = None,
    agents_by_id: dict[int, dict] | None = None,
) -> ApplicationRead:
    tl = build_timeline_for_application(
        states_ordered=states_ordered,
        current_status_name=status.status,
        today=today,
    )
    reminders = [
        ReminderRead(kind=r.kind, fire_on=r.fire_on, label=r.label) for r in tl.upcoming_reminders
    ]
    filing_date = tl.filing_date or state.application_date
    client_summary = _resolve_client_summary(session, data.client_id, clients_by_id)
    attorney_summary = _resolve_attorney_summary(session, data.attorney_id, agents_by_id)
    return ApplicationRead(
        id=data.id or 0,
        project_code=data.project_code,
        application_number=data.application_num,
        application_date=filing_date,
        status_date=state.application_date,
        applicant_name=data.applicant_name,
        applicant_address=data.applicant_address,
        application_title=data.application_title,
        client_id=data.client_id,
        attorney_id=data.attorney_id,
        client=client_summary,
        attorney=attorney_summary,
        application_current_status=status.status,
        comments=data.comments,
        filing_date=tl.filing_date,
        fer_response_deadline=tl.fer_response_deadline,
        upcoming_reminders=reminders,
        last_status_updated_at=data.last_status_updated_at,
    )


def _filled_status_dates(session: Session, application_num: str) -> dict[int, date]:
    states = session.exec(
        select(ApplicationState).where(ApplicationState.application_num == application_num)
    ).all()
    by_status_id: dict[int, ApplicationState] = {}
    for state in states:
        existing = by_status_id.get(state.status_id)
        if not existing or (state.id or 0) > (existing.id or 0):
            by_status_id[state.status_id] = state
    return {sid: st.application_date for sid, st in by_status_id.items()}


def list_statuses(session: Session) -> List[StatusRead]:
    rows = session.exec(select(Status).order_by(Status.id)).all()
    return [StatusRead(id=row.id or 0, status=row.status) for row in rows]


def create_application(session: Session, application: ApplicationCreate) -> ApplicationRead:
    status_row = session.get(Status, STATUS_ID_APPLICATION_FILED)
    if not status_row:
        raise ValueError("status table must contain Application Filed before creating applications")

    now = _utcnow()
    db_application = ApplicationData(
        project_code=application.project_code,
        application_num=application.application_number,
        applicant_name=application.applicant_name,
        client_id=application.client_id,
        attorney_id=application.attorney_id,
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
        _touch_last_status_updated(db_application, now)
        session.commit()
        session.refresh(db_application)
        session.refresh(db_state)
    except IntegrityError as exc:
        session.rollback()
        msg = str(exc).lower()
        if "project_code" in msg:
            raise ValueError("project_code already exists") from exc
        raise ValueError("application_number already exists or violates constraints") from exc

    today = date.today()
    states = [(db_state.id or 0, db_state.application_date, status_row.status)]
    return _read_model_with_timeline(session, db_application, db_state, status_row, states, today)


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
    clients_by_id, agents_by_id = _load_contacts_bulk(
        session, [data for data, _state, _status in rows]
    )
    return [
        _read_model_with_timeline(
            session,
            data,
            state,
            status,
            grouped.get(data.application_num, []),
            today,
            clients_by_id,
            agents_by_id,
        )
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
    return _read_model_with_timeline(session, data, state, status, states, today)


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

    if "project_code" in update_dict:
        db_application.project_code = update_dict["project_code"]

    if "applicant_name" in update_dict:
        db_application.applicant_name = update_dict["applicant_name"]
    if "client_id" in update_dict:
        db_application.client_id = update_dict["client_id"]
    if "attorney_id" in update_dict:
        db_application.attorney_id = update_dict["attorney_id"]
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

    to_add: dict[tuple[int | None, int], ApplicationState] = {}
    for state in states_to_update:
        to_add[(state.id, id(state))] = state
    for state in filed_rows:
        to_add[(state.id, id(state))] = state

    try:
        session.add(db_application)
        for state in to_add.values():
            session.add(state)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        msg = str(exc).lower()
        if "project_code" in msg:
            raise ValueError("project_code already exists") from exc
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

    existing_filled = _filled_status_dates(session, db_application.application_num)
    validate_status_change(
        existing_filled,
        status_update.status_id,
        status_update.application_date,
    )

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
    _touch_last_status_updated(db_application, now)
    session.commit()
    return get_application_by_id(session, application_id)


def delete_application(session: Session, application_id: int) -> bool:
    db_application = session.get(ApplicationData, application_id)
    if not db_application:
        return False

    session.delete(db_application)
    session.commit()
    return True


def get_project_detail(session: Session, application_id: int) -> Optional[ProjectDetailRead]:
    app_read = get_application_by_id(session, application_id)
    if not app_read:
        return None

    db_application = session.get(ApplicationData, application_id)
    if not db_application:
        return None

    states = session.exec(
        select(ApplicationState).where(ApplicationState.application_num == db_application.application_num)
    ).all()
    by_status_id: dict[int, ApplicationState] = {}
    for state in states:
        existing = by_status_id.get(state.status_id)
        if not existing or (state.id or 0) > (existing.id or 0):
            by_status_id[state.status_id] = state

    filled = {
        sid: st.application_date
        for sid, st in by_status_id.items()
    }
    enabled = enabled_status_ids(filled)
    statuses = session.exec(select(Status).order_by(Status.id)).all()
    timeline = [
        ProjectTimelineItem(
            status_id=status.id or 0,
            status_name=status.status,
            application_date=by_status_id.get(status.id or 0).application_date
            if by_status_id.get(status.id or 0)
            else None,
            is_optional=is_optional_status(status.id or 0),
            is_enabled=(status.id or 0) in enabled,
        )
        for status in statuses
    ]

    return ProjectDetailRead(
        id=app_read.id,
        project_code=app_read.project_code,
        application_number=app_read.application_number,
        application_date=app_read.application_date,
        applicant_name=app_read.applicant_name,
        applicant_address=app_read.applicant_address,
        application_title=app_read.application_title,
        client_id=app_read.client_id,
        attorney_id=app_read.attorney_id,
        client=app_read.client,
        attorney=app_read.attorney,
        application_current_status=app_read.application_current_status,
        comments=app_read.comments,
        timeline=timeline,
    )


def update_project_detail(
    session: Session, application_id: int, detail_update: ProjectDetailUpdate
) -> Optional[ProjectDetailRead]:
    updated_app = update_application(session, application_id, detail_update.application)
    if not updated_app:
        return None

    db_application = session.get(ApplicationData, application_id)
    if not db_application:
        return None

    now = _utcnow()

    incoming_status_ids = {item.status_id for item in detail_update.timeline_updates}
    for status_id in incoming_status_ids:
        if not session.get(Status, status_id):
            raise ValueError(f"invalid status_id: {status_id}")

    validate_timeline_updates(
        [(item.status_id, item.application_date) for item in detail_update.timeline_updates]
    )

    existing_states = session.exec(
        select(ApplicationState)
        .where(ApplicationState.application_num == db_application.application_num)
        .order_by(desc(ApplicationState.id))
    ).all()

    latest_by_status_id: dict[int, ApplicationState] = {}
    for state in existing_states:
        if state.status_id not in incoming_status_ids:
            session.delete(state)
            continue
        if state.status_id in latest_by_status_id:
            session.delete(state)
            continue
        latest_by_status_id[state.status_id] = state

    for item in detail_update.timeline_updates:
        db_state = latest_by_status_id.get(item.status_id)
        if db_state:
            db_state.application_date = item.application_date
            db_state.modified_date = now
        else:
            db_state = ApplicationState(
                application_num=db_application.application_num,
                status_id=item.status_id,
                application_date=item.application_date,
                created_date=now,
                modified_date=now,
            )
        session.add(db_state)

    if detail_update.timeline_updates:
        _touch_last_status_updated(db_application, now)

    session.commit()
    return get_project_detail(session, application_id)
