import json
import re
from collections import defaultdict
from datetime import date, datetime
from typing import DefaultDict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, desc, select

from app.domain.tm_status_workflow import (
    enabled_status_ids,
    is_optional_status,
    validate_status_change,
    validate_timeline_updates,
)
from app.domain.custom_events import REMINDER_OPTION_NONE, compute_reminder_date, format_short_date
from app.domain.tm_timeline import build_timeline_for_tm_application
from app.patents.models import PatentAgent, PatentClient
from app.tm_class_catalog import MULTI_CLASS_MAIN_VALUE, class_description_for
from app.models.trademark import (
    TmApplicationData,
    TmApplicationState,
    TmCustomEvent,
    TmProjectNote,
    TmStatus,
)
from app.schemas.trademark import (
    TmApplicationCreate,
    TmApplicationRead,
    TmApplicationStatusUpdate,
    TmApplicationTimelineEventRead,
    TmApplicationTimelineRead,
    TmApplicationUpdate,
    TmCustomEventClose,
    TmCustomEventCreate,
    TmCustomEventRead,
    TmProjectDetailRead,
    TmProjectDetailUpdate,
    TmProjectNoteInput,
    TmProjectNoteRead,
    TmProjectTimelineItem,
    TmReminderRead,
    TmStatusRead,
)
from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED
from app.audit.service import record_status_change


_PROJECT_CODE_PATTERN = re.compile(r"^TM(\d{4,})$")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _generate_next_project_code(session: Session) -> str:
    existing_codes = session.exec(select(TmApplicationData.project_code)).all()
    max_num = 0
    for code in existing_codes:
        match = _PROJECT_CODE_PATTERN.match(code or "")
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"TM{max_num + 1:04d}"


def _serialize_selected_classes(values: Optional[List[str]]) -> Optional[str]:
    if not values:
        return None
    return json.dumps(list(values))


def _parse_selected_classes(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(v) for v in parsed] if isinstance(parsed, list) else []


def _serialize_class_descriptions(entries) -> Optional[str]:
    """Accepts either TmClassDescriptionEntry objects (create path) or plain
    dicts (update path, after model_dump()) and stores them as a JSON list."""
    if not entries:
        return None
    normalized = []
    for entry in entries:
        if isinstance(entry, dict):
            normalized.append(
                {"class_no": str(entry.get("class_no")), "description": str(entry.get("description") or "")}
            )
        else:
            normalized.append({"class_no": entry.class_no, "description": entry.description or ""})
    return json.dumps(normalized)


def _parse_class_descriptions(raw: Optional[str]) -> List[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    result = []
    for item in parsed:
        if isinstance(item, dict) and "class_no" in item:
            result.append({"class_no": str(item.get("class_no")), "description": str(item.get("description") or "")})
    return result


def _touch_last_status_updated(db_application: TmApplicationData, when: Optional[datetime] = None) -> None:
    ts = when or _utcnow()
    db_application.last_status_updated_at = ts
    db_application.modified_date = ts


def _states_ordered_for_app(session: Session, application_num: str) -> List[Tuple[int, date, str]]:
    rows = session.exec(
        select(TmApplicationState, TmStatus)
        .join(TmStatus)
        .where(TmApplicationState.application_num == application_num)
        .order_by(TmApplicationState.id)
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
        select(TmApplicationState, TmStatus)
        .join(TmStatus)
        .where(TmApplicationState.application_num.in_(nums))
        .order_by(TmApplicationState.application_num, TmApplicationState.id)
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


def _custom_event_reminder_row(row: TmCustomEvent) -> TmReminderRead:
    return TmReminderRead(
        kind="custom_event",
        fire_on=row.reminder_date,
        label=f"{row.event_type} issued on {format_short_date(row.event_date)}",
    )


def _custom_event_reminders(session: Session, application_id: int) -> List[TmReminderRead]:
    """Unclosed custom events with a reminder date, as TmReminderRead rows -
    folded into upcoming_reminders so they ride the existing header/deadlines
    plumbing for free. Closed events never surface here."""
    rows = session.exec(
        select(TmCustomEvent).where(
            TmCustomEvent.application_id == application_id,
            TmCustomEvent.closure_date.is_(None),
            TmCustomEvent.reminder_date.is_not(None),
        )
    ).all()
    return [_custom_event_reminder_row(row) for row in rows]


def _custom_event_reminders_bulk(
    session: Session, application_ids: List[int]
) -> dict[int, List[TmReminderRead]]:
    ids = [i for i in application_ids if i]
    if not ids:
        return {}
    rows = session.exec(
        select(TmCustomEvent).where(
            TmCustomEvent.application_id.in_(ids),
            TmCustomEvent.closure_date.is_(None),
            TmCustomEvent.reminder_date.is_not(None),
        )
    ).all()
    grouped: DefaultDict[int, List[TmReminderRead]] = defaultdict(list)
    for row in rows:
        grouped[row.application_id].append(_custom_event_reminder_row(row))
    return dict(grouped)


def _read_model_with_timeline(
    session: Session,
    data: TmApplicationData,
    state: TmApplicationState,
    status: TmStatus,
    states_ordered: List[Tuple[int, date, str]],
    today: date,
    clients_by_id: dict[int, dict] | None = None,
    agents_by_id: dict[int, dict] | None = None,
    custom_event_reminders_by_app_id: dict[int, List[TmReminderRead]] | None = None,
) -> TmApplicationRead:
    tl = build_timeline_for_tm_application(
        states_ordered=states_ordered,
        current_status_name=status.status,
        today=today,
    )
    reminders = [
        TmReminderRead(kind=r.kind, fire_on=r.fire_on, label=r.label) for r in tl.upcoming_reminders
    ]
    custom_reminders = (
        custom_event_reminders_by_app_id.get(data.id or 0, [])
        if custom_event_reminders_by_app_id is not None
        else _custom_event_reminders(session, data.id or 0)
    )
    reminders = sorted(reminders + custom_reminders, key=lambda r: (r.fire_on, r.kind))
    filing_date = tl.filing_date or state.application_date
    client_summary = _resolve_client_summary(session, data.client_id, clients_by_id)
    attorney_summary = _resolve_attorney_summary(session, data.attorney_id, agents_by_id)
    return TmApplicationRead(
        id=data.id or 0,
        project_code=data.project_code,
        application_number=data.application_num,
        application_date=filing_date,
        status_date=state.application_date,
        applicant_name=data.applicant_name,
        applicant_type=data.applicant_type,
        tm_name=data.tm_name,
        tm_type=data.tm_type,
        tm_class=data.tm_class,
        tm_class_description=class_description_for(data.tm_class),
        is_multi_class=data.is_multi_class,
        tm_selected_classes=_parse_selected_classes(data.tm_selected_classes),
        application_class_descriptions=_parse_class_descriptions(data.application_class_description),
        applicant_address=data.applicant_address,
        client_id=data.client_id,
        attorney_id=data.attorney_id,
        client_docket_no=data.client_docket_no,
        client=client_summary,
        attorney=attorney_summary,
        application_current_status=status.status,
        comments=data.comments,
        filing_date=tl.filing_date,
        fer_followup_due=tl.fer_followup_due,
        hearing_due=tl.hearing_due,
        upcoming_reminders=reminders,
        last_status_updated_at=data.last_status_updated_at,
    )


def _filled_status_dates(session: Session, application_num: str) -> dict[int, date]:
    states = session.exec(
        select(TmApplicationState).where(TmApplicationState.application_num == application_num)
    ).all()
    by_status_id: dict[int, TmApplicationState] = {}
    for state in states:
        existing = by_status_id.get(state.status_id)
        if not existing or (state.id or 0) > (existing.id or 0):
            by_status_id[state.status_id] = state
    return {sid: st.application_date for sid, st in by_status_id.items()}


def list_tm_statuses(session: Session) -> List[TmStatusRead]:
    rows = session.exec(select(TmStatus).order_by(TmStatus.id)).all()
    return [TmStatusRead(id=row.id or 0, status=row.status) for row in rows]


def create_tm_application(session: Session, application: TmApplicationCreate) -> TmApplicationRead:
    status_row = session.get(TmStatus, STATUS_ID_TM_APPLICATION_FILED)
    if not status_row:
        raise ValueError("tm_status table must contain Application filed before creating applications")

    now = _utcnow()
    last_error: Optional[IntegrityError] = None

    for _ in range(5):
        db_application = TmApplicationData(
            project_code=_generate_next_project_code(session),
            application_num=application.application_number,
            applicant_name=application.applicant_name,
            applicant_type=application.applicant_type,
            tm_name=application.tm_name,
            tm_type=application.tm_type,
            tm_class=application.tm_class,
            is_multi_class=application.is_multi_class,
            tm_selected_classes=_serialize_selected_classes(application.tm_selected_classes),
            application_class_description=_serialize_class_descriptions(application.application_class_descriptions),
            client_id=application.client_id,
            attorney_id=application.attorney_id,
            client_docket_no=application.client_docket_no,
            applicant_address=application.applicant_address,
            comments=application.comments,
            created_date=now,
            modified_date=now,
        )

        try:
            session.add(db_application)
            session.flush()

            db_state = TmApplicationState(
                application_num=application.application_number,
                status_id=STATUS_ID_TM_APPLICATION_FILED,
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
                # Auto-generated code collided with a concurrent create - regenerate and retry.
                last_error = exc
                continue
            raise ValueError("application_number already exists or violates constraints") from exc

        today = date.today()
        states = [(db_state.id or 0, db_state.application_date, status_row.status)]
        return _read_model_with_timeline(session, db_application, db_state, status_row, states, today)

    raise ValueError("Unable to generate a unique project code, please retry.") from last_error


def get_tm_applications(session: Session) -> List[TmApplicationRead]:
    latest_state_subquery = (
        select(
            TmApplicationState.application_num.label("application_num"),
            func.max(TmApplicationState.id).label("latest_state_id"),
        )
        .group_by(TmApplicationState.application_num)
        .subquery()
    )

    query = (
        select(TmApplicationData, TmApplicationState, TmStatus)
        .join(
            latest_state_subquery,
            latest_state_subquery.c.application_num == TmApplicationData.application_num,
        )
        .join(TmApplicationState, TmApplicationState.id == latest_state_subquery.c.latest_state_id)
        .join(TmStatus, TmStatus.id == TmApplicationState.status_id)
        .order_by(desc(TmApplicationState.application_date), desc(TmApplicationState.id))
    )
    rows = session.exec(query).all()
    today = date.today()
    nums = [data.application_num for data, _state, _status in rows]
    grouped = _states_grouped(session, nums)
    clients_by_id, agents_by_id = _load_contacts_bulk(
        session, [data for data, _state, _status in rows]
    )
    custom_reminders_by_app_id = _custom_event_reminders_bulk(
        session, [data.id for data, _state, _status in rows if data.id]
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
            custom_reminders_by_app_id,
        )
        for data, state, status in rows
    ]


def get_tm_application_by_id(session: Session, application_id: int) -> Optional[TmApplicationRead]:
    latest_state_subquery = (
        select(
            TmApplicationState.application_num.label("application_num"),
            func.max(TmApplicationState.id).label("latest_state_id"),
        )
        .group_by(TmApplicationState.application_num)
        .subquery()
    )

    query = (
        select(TmApplicationData, TmApplicationState, TmStatus)
        .join(
            latest_state_subquery,
            latest_state_subquery.c.application_num == TmApplicationData.application_num,
        )
        .join(TmApplicationState, TmApplicationState.id == latest_state_subquery.c.latest_state_id)
        .join(TmStatus, TmStatus.id == TmApplicationState.status_id)
        .where(TmApplicationData.id == application_id)
    )
    row = session.exec(query).first()
    if not row:
        return None
    data, state, status = row
    today = date.today()
    states = _states_ordered_for_app(session, data.application_num)
    return _read_model_with_timeline(session, data, state, status, states, today)


def get_tm_application_timeline(session: Session, application_id: int) -> Optional[TmApplicationTimelineRead]:
    db_application = session.get(TmApplicationData, application_id)
    if not db_application:
        return None
    states = _states_ordered_for_app(session, db_application.application_num)
    current_status = states[-1][2] if states else ""

    today = date.today()
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=current_status,
        today=today,
    )

    reminders = [
        TmReminderRead(kind=r.kind, fire_on=r.fire_on, label=r.label) for r in tl.upcoming_reminders
    ]

    raw_states = session.exec(
        select(TmApplicationState, TmStatus)
        .join(TmStatus)
        .where(TmApplicationState.application_num == db_application.application_num)
        .order_by(TmApplicationState.id)
    ).all()
    events = [
        TmApplicationTimelineEventRead(
            state_id=st.id or 0,
            status=meta.status,
            application_date=st.application_date,
        )
        for st, meta in raw_states
    ]

    return TmApplicationTimelineRead(
        application_number=db_application.application_num,
        filing_date=tl.filing_date,
        fer_followup_due=tl.fer_followup_due,
        hearing_due=tl.hearing_due,
        upcoming_reminders=reminders,
        events=events,
    )


def update_tm_application(
    session: Session, application_id: int, update_data: TmApplicationUpdate
) -> Optional[TmApplicationRead]:
    db_application = session.get(TmApplicationData, application_id)
    if not db_application:
        return None

    old_number = db_application.application_num
    update_dict = update_data.model_dump(exclude_unset=True)
    now = _utcnow()

    db_state = session.exec(
        select(TmApplicationState)
        .where(TmApplicationState.application_num == old_number)
        .order_by(desc(TmApplicationState.id))
    ).first()
    if not db_state:
        status_row = session.get(TmStatus, STATUS_ID_TM_APPLICATION_FILED)
        if not status_row:
            return None
        filing_date = update_dict.get("application_date", date.today())
        db_state = TmApplicationState(
            application_num=db_application.application_num,
            status_id=STATUS_ID_TM_APPLICATION_FILED,
            application_date=filing_date,
            created_date=now,
            modified_date=now,
        )
        session.add(db_state)
        session.flush()

    new_number = update_dict.get("application_number", old_number)
    if "application_number" in update_dict:
        db_application.application_num = new_number

    # project_code is system-generated and immutable - never written here even
    # if a caller still sends one.
    if "applicant_name" in update_dict:
        db_application.applicant_name = update_dict["applicant_name"]
    if "applicant_type" in update_dict:
        db_application.applicant_type = update_dict["applicant_type"]
    if "client_id" in update_dict:
        db_application.client_id = update_dict["client_id"]
    if "attorney_id" in update_dict:
        db_application.attorney_id = update_dict["attorney_id"]
    if "client_docket_no" in update_dict:
        db_application.client_docket_no = update_dict["client_docket_no"]
    if "tm_name" in update_dict:
        db_application.tm_name = update_dict["tm_name"]
    if "tm_type" in update_dict:
        db_application.tm_type = update_dict["tm_type"]
    if "applicant_address" in update_dict:
        db_application.applicant_address = update_dict["applicant_address"]
    if "comments" in update_dict:
        db_application.comments = update_dict["comments"]
    if "application_class_descriptions" in update_dict:
        db_application.application_class_description = _serialize_class_descriptions(
            update_dict["application_class_descriptions"]
        )

    class_mode_touched = any(
        key in update_dict for key in ("is_multi_class", "tm_class", "tm_selected_classes")
    )
    if class_mode_touched:
        effective_is_multi = update_dict.get("is_multi_class", db_application.is_multi_class)
        effective_class = update_dict.get("tm_class", db_application.tm_class)
        effective_selected = update_dict.get(
            "tm_selected_classes", _parse_selected_classes(db_application.tm_selected_classes)
        )
        if effective_is_multi:
            if effective_class != MULTI_CLASS_MAIN_VALUE:
                raise ValueError("tm_class must be '99' for a multi class application.")
            if not effective_selected:
                raise ValueError("Select at least one class for a multi class application.")
        else:
            if effective_class == MULTI_CLASS_MAIN_VALUE:
                raise ValueError("tm_class must be a specific class (1-45) for a single class application.")
            if effective_selected:
                raise ValueError("tm_selected_classes must be empty for a single class application.")
        db_application.is_multi_class = effective_is_multi
        db_application.tm_class = effective_class
        db_application.tm_selected_classes = _serialize_selected_classes(effective_selected)

    db_application.modified_date = now

    states_to_update: List[TmApplicationState] = [db_state]
    if "application_number" in update_dict and new_number != old_number:
        all_states = session.exec(
            select(TmApplicationState).where(TmApplicationState.application_num == old_number)
        ).all()
        for state in all_states:
            state.application_num = new_number
            state.modified_date = now
        states_to_update = all_states

    filed_rows: List[TmApplicationState] = []

    if "application_date" in update_dict:
        new_date_val = update_dict["application_date"]
        filed_rows = session.exec(
            select(TmApplicationState)
            .where(
                TmApplicationState.application_num == db_application.application_num,
                TmApplicationState.status_id == STATUS_ID_TM_APPLICATION_FILED,
            )
            .order_by(TmApplicationState.id)
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

    to_add: dict[tuple[int | None, int], TmApplicationState] = {}
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

    return get_tm_application_by_id(session, application_id)


def update_tm_application_status(
    session: Session, application_id: int, status_update: TmApplicationStatusUpdate
) -> Optional[TmApplicationRead]:
    db_application = session.get(TmApplicationData, application_id)
    if not db_application:
        return None

    status_row = session.get(TmStatus, status_update.status_id)
    if not status_row:
        raise ValueError("invalid status_id")

    # Capture previous status name BEFORE any new state row is added
    old_status_name = None
    prev = session.exec(
        select(TmApplicationState, TmStatus)
        .join(TmStatus)
        .where(TmApplicationState.application_num == db_application.application_num)
        .order_by(desc(TmApplicationState.id))
    ).first()
    if prev is not None:
        old_status_name = prev[1].status

    existing_filled = _filled_status_dates(session, db_application.application_num)
    validate_status_change(
        existing_filled,
        status_update.status_id,
        status_update.application_date,
    )

    now = _utcnow()
    db_state = session.exec(
        select(TmApplicationState)
        .where(
            TmApplicationState.application_num == db_application.application_num,
            TmApplicationState.status_id == status_update.status_id,
        )
        .order_by(desc(TmApplicationState.id))
    ).first()

    if db_state:
        db_state.application_date = status_update.application_date
        db_state.modified_date = now
    else:
        db_state = TmApplicationState(
            application_num=db_application.application_num,
            status_id=status_update.status_id,
            application_date=status_update.application_date,
            created_date=now,
            modified_date=now,
        )
    session.add(db_state)
    _touch_last_status_updated(db_application, now)
    record_status_change(
        session,
        entity_type="trademark",
        entity_id=db_application.id,
        entity_label=db_application.project_code,
        old_status=old_status_name,
        new_status=status_row.status,
    )
    session.commit()
    return get_tm_application_by_id(session, application_id)


def delete_tm_application(session: Session, application_id: int) -> bool:
    db_application = session.get(TmApplicationData, application_id)
    if not db_application:
        return False
    session.delete(db_application)
    session.commit()
    return True


def _project_notes_read(session: Session, application_id: int) -> List[TmProjectNoteRead]:
    rows = session.exec(
        select(TmProjectNote)
        .where(TmProjectNote.application_id == application_id)
        .order_by(desc(TmProjectNote.created_date), desc(TmProjectNote.id))
    ).all()
    return [TmProjectNoteRead(id=n.id, note_text=n.note_text, created_date=n.created_date) for n in rows]


def add_project_note(
    session: Session, application_id: int, payload: TmProjectNoteInput
) -> Optional[List[TmProjectNoteRead]]:
    application = session.get(TmApplicationData, application_id)
    if not application:
        return None
    note_text = payload.note_text.strip()
    if not note_text:
        raise ValueError("Note text is required")
    session.add(TmProjectNote(application_id=application_id, note_text=note_text))
    session.commit()
    return _project_notes_read(session, application_id)


def update_project_note(
    session: Session, application_id: int, note_id: int, payload: TmProjectNoteInput
) -> Optional[List[TmProjectNoteRead]]:
    application = session.get(TmApplicationData, application_id)
    if not application:
        return None
    note = session.get(TmProjectNote, note_id)
    if not note or note.application_id != application_id:
        return None
    note_text = payload.note_text.strip()
    if not note_text:
        raise ValueError("Note text is required")
    note.note_text = note_text
    session.add(note)
    session.commit()
    return _project_notes_read(session, application_id)


def _tm_custom_events_read(session: Session, application_id: int) -> List[TmCustomEventRead]:
    rows = session.exec(
        select(TmCustomEvent)
        .where(TmCustomEvent.application_id == application_id)
        .order_by(desc(TmCustomEvent.event_date), desc(TmCustomEvent.id))
    ).all()
    return [
        TmCustomEventRead(
            id=row.id,
            event_type=row.event_type,
            event_date=row.event_date,
            reminder_option=row.reminder_option,
            reminder_date=row.reminder_date,
            closure_date=row.closure_date,
            created_date=row.created_date,
        )
        for row in rows
    ]


def add_tm_custom_event(
    session: Session, application_id: int, payload: TmCustomEventCreate
) -> Optional[List[TmCustomEventRead]]:
    application = session.get(TmApplicationData, application_id)
    if not application:
        return None
    reminder_date = compute_reminder_date(payload.event_date, payload.reminder_option)
    session.add(
        TmCustomEvent(
            application_id=application_id,
            event_type=payload.event_type.strip(),
            event_date=payload.event_date,
            reminder_option=payload.reminder_option,
            reminder_date=reminder_date,
        )
    )
    session.commit()
    return _tm_custom_events_read(session, application_id)


def close_tm_custom_event(
    session: Session, application_id: int, event_id: int, payload: TmCustomEventClose
) -> Optional[List[TmCustomEventRead]]:
    application = session.get(TmApplicationData, application_id)
    if not application:
        return None
    event = session.get(TmCustomEvent, event_id)
    if not event or event.application_id != application_id:
        return None
    if event.closure_date is not None:
        raise ValueError("Event is already closed")
    event.closure_date = payload.closure_date
    session.add(event)
    session.commit()
    return _tm_custom_events_read(session, application_id)


def delete_tm_custom_event(
    session: Session, application_id: int, event_id: int
) -> Optional[List[TmCustomEventRead]]:
    application = session.get(TmApplicationData, application_id)
    if not application:
        return None
    event = session.get(TmCustomEvent, event_id)
    if not event or event.application_id != application_id:
        return None
    if event.reminder_option != REMINDER_OPTION_NONE or event.closure_date is not None:
        raise ValueError("Only open, no-reminder events can be deleted")
    session.delete(event)
    session.commit()
    return _tm_custom_events_read(session, application_id)


def get_tm_project_detail(session: Session, application_id: int) -> Optional[TmProjectDetailRead]:
    app_read = get_tm_application_by_id(session, application_id)
    if not app_read:
        return None

    db_application = session.get(TmApplicationData, application_id)
    if not db_application:
        return None

    states = session.exec(
        select(TmApplicationState).where(
            TmApplicationState.application_num == db_application.application_num
        )
    ).all()
    by_status_id: dict[int, TmApplicationState] = {}
    for state in states:
        existing = by_status_id.get(state.status_id)
        if not existing or (state.id or 0) > (existing.id or 0):
            by_status_id[state.status_id] = state

    filled = {sid: st.application_date for sid, st in by_status_id.items()}
    enabled = enabled_status_ids(filled)
    statuses = session.exec(select(TmStatus).order_by(TmStatus.id)).all()
    timeline = [
        TmProjectTimelineItem(
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

    return TmProjectDetailRead(
        id=app_read.id,
        project_code=app_read.project_code,
        application_number=app_read.application_number,
        application_date=app_read.application_date,
        applicant_name=app_read.applicant_name,
        applicant_type=app_read.applicant_type,
        tm_name=app_read.tm_name,
        tm_type=app_read.tm_type,
        tm_class=app_read.tm_class,
        tm_class_description=class_description_for(app_read.tm_class),
        is_multi_class=app_read.is_multi_class,
        tm_selected_classes=app_read.tm_selected_classes,
        application_class_descriptions=app_read.application_class_descriptions,
        applicant_address=app_read.applicant_address,
        client_id=app_read.client_id,
        attorney_id=app_read.attorney_id,
        client=app_read.client,
        attorney=app_read.attorney,
        application_current_status=app_read.application_current_status,
        comments=app_read.comments,
        filing_date=app_read.filing_date,
        fer_followup_due=app_read.fer_followup_due,
        hearing_due=app_read.hearing_due,
        upcoming_reminders=app_read.upcoming_reminders,
        notes=_project_notes_read(session, application_id),
        custom_events=_tm_custom_events_read(session, application_id),
        timeline=timeline,
    )


def update_tm_project_detail(
    session: Session, application_id: int, detail_update: TmProjectDetailUpdate
) -> Optional[TmProjectDetailRead]:
    updated_app = update_tm_application(session, application_id, detail_update.application)
    if not updated_app:
        return None

    db_application = session.get(TmApplicationData, application_id)
    if not db_application:
        return None

    now = _utcnow()

    incoming_status_ids = {item.status_id for item in detail_update.timeline_updates}
    for status_id in incoming_status_ids:
        if not session.get(TmStatus, status_id):
            raise ValueError(f"invalid status_id: {status_id}")

    validate_timeline_updates(
        [(item.status_id, item.application_date) for item in detail_update.timeline_updates]
    )

    existing_states = session.exec(
        select(TmApplicationState)
        .where(TmApplicationState.application_num == db_application.application_num)
        .order_by(desc(TmApplicationState.id))
    ).all()

    latest_by_status_id: dict[int, TmApplicationState] = {}
    for state in existing_states:
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
            db_state = TmApplicationState(
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
    return get_tm_project_detail(session, application_id)
