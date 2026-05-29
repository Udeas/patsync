from __future__ import annotations

import json
from datetime import datetime

from sqlmodel import Session, select

from .models import (
    PatentAgent,
    PatentClient,
    PatentInternationalApplication,
    PatentInventor,
    PatentPriority,
    PatentProject,
    PatentStatusEvent,
)
from .patent_status_catalog import STATUS_ID_APPLICATION_FILED
from .reminders import compute_next_patent_action
from .patent_status_catalog import ALL_STATUS_IDS
from .schemas import (
    PatentAgentInput,
    PatentClientInput,
    PatentDraftFinalizeRequest,
    PatentProjectCreate,
    PatentProjectDetailUpdate,
    PatentProjectUpdate,
)
from .validators import parse_in_application_number, validate_create_project_filing_windows
from .workflow import derive_current_status, validate_timeline_updates


def _seed_application_filed_if_final(
    session: Session,
    project: PatentProject,
) -> None:
    if project.project_stage != "final" and project.project_mode != "final":
        return
    if not project.in_application_date:
        return
    existing = session.exec(
        select(PatentStatusEvent).where(
            PatentStatusEvent.project_id == project.id,
            PatentStatusEvent.status_id == STATUS_ID_APPLICATION_FILED,
        )
    ).first()
    if existing:
        return
    session.add(
        PatentStatusEvent(
            project_id=project.id,
            status_id=STATUS_ID_APPLICATION_FILED,
            status_date=project.in_application_date,
        )
    )


def _load_project_relations(session: Session, project: PatentProject) -> dict:
    inventors = session.exec(
        select(PatentInventor)
        .where(PatentInventor.project_id == project.id)
        .order_by(PatentInventor.id.asc())
    ).all()
    priorities = session.exec(
        select(PatentPriority)
        .where(PatentPriority.project_id == project.id)
        .order_by(PatentPriority.priority_application_date.asc(), PatentPriority.id.asc())
    ).all()
    international_apps = session.exec(
        select(PatentInternationalApplication)
        .where(PatentInternationalApplication.project_id == project.id)
        .order_by(
            PatentInternationalApplication.international_application_date.asc(),
            PatentInternationalApplication.id.asc(),
        )
    ).all()
    status_events = session.exec(
        select(PatentStatusEvent)
        .where(PatentStatusEvent.project_id == project.id)
        .order_by(PatentStatusEvent.status_date.asc(), PatentStatusEvent.status_id.asc())
    ).all()

    attorney = None
    if project.attorney_id:
        agent = session.get(PatentAgent, project.attorney_id)
        if agent:
            attorney = {
                "id": agent.id,
                "name": agent.name,
                "agent_code": agent.agent_code,
                "address": agent.address,
                "mobile_1": agent.mobile_1,
                "mobile_2": agent.mobile_2,
                "email_1": agent.email_1,
                "email_2": agent.email_2,
            }

    client = None
    if project.client_id:
        patent_client = session.get(PatentClient, project.client_id)
        if patent_client:
            client = {
                "id": patent_client.id,
                "client_code": patent_client.client_code,
                "name": patent_client.name,
            }

    return {
        "inventors": [
            {
                "name": inv.name,
                "nationality": inv.nationality,
                "address": inv.address,
            }
            for inv in inventors
        ],
        "priorities": [
            {
                "priority_application_no": p.priority_application_no,
                "priority_application_date": p.priority_application_date,
                "country": p.country,
                "title": p.title,
            }
            for p in priorities
        ],
        "international_applications": [
            {
                "international_application_no": ia.international_application_no,
                "international_application_date": ia.international_application_date,
            }
            for ia in international_apps
        ],
        "status_events": [
            {"status_id": event.status_id, "status_date": event.status_date}
            for event in status_events
        ],
        "attorney": attorney,
        "client": client,
        "_status_events_raw": status_events,
    }


def _project_to_response(session: Session, project: PatentProject) -> dict:
    relations = _load_project_relations(session, project)
    status_events_raw = relations.pop("_status_events_raw")
    filled_status = {event.status_id: event.status_date for event in status_events_raw}
    current_status = derive_current_status(filled_status)
    priority_dates = [
        p["priority_application_date"] for p in relations["priorities"]
    ]
    next_action = compute_next_patent_action(
        filled=filled_status,
        current_status_id=current_status[0] if current_status else None,
        in_application_date=project.in_application_date,
        priority_dates=priority_dates,
    )
    due_action = next_action.message if next_action else None
    action_due_date = next_action.due_date if next_action else None
    return {
        "id": project.id,
        "project_mode": project.project_mode,
        "project_stage": project.project_stage,
        "docket_no": project.docket_no,
        "in_application_no": project.in_application_no,
        "in_application_date": project.in_application_date,
        "applicant_name": project.applicant_name,
        "applicant_country": project.applicant_country,
        "applicant_address": project.applicant_address,
        "application_title": project.application_title,
        "application_type": project.application_type,
        "provisional_kind": project.provisional_kind,
        "pct_wipo_filed_only": project.pct_wipo_filed_only,
        "client_docket_no": project.client_docket_no,
        "current_status_id": current_status[0] if current_status else None,
        "current_status_date": current_status[1] if current_status else None,
        "due_action": due_action,
        "action_due_date": action_due_date,
        **relations,
    }


def _persist_priorities_and_international(
    session: Session,
    project_id: int,
    payload: PatentProjectCreate,
) -> None:
    for priority in payload.priorities:
        session.add(
            PatentPriority(
                project_id=project_id,
                priority_application_no=priority.priority_application_no,
                priority_application_date=priority.priority_application_date,
                country=priority.country.upper(),
                title=priority.title,
            )
        )

    international_rows = list(payload.international_applications)
    if not international_rows and payload.international_application_no and payload.international_application_date:
        from .schemas import PatentInternationalInput

        international_rows = [
            PatentInternationalInput(
                international_application_no=payload.international_application_no,
                international_application_date=payload.international_application_date,
            )
        ]

    for row in international_rows:
        session.add(
            PatentInternationalApplication(
                project_id=project_id,
                international_application_no=row.international_application_no,
                international_application_date=row.international_application_date,
            )
        )


def create_project(session: Session, payload: PatentProjectCreate) -> dict:
    existing = session.exec(select(PatentProject).where(PatentProject.docket_no == payload.docket_no)).first()
    if existing:
        raise ValueError("Docket number already exists")

    if payload.project_mode == "final" and not payload.in_application_no:
        raise ValueError("IN application number is required for final projects")
    if payload.project_mode == "final" and not payload.in_application_date:
        raise ValueError("IN application date is required for final projects")

    if payload.in_application_no:
        parse_in_application_number(payload.in_application_no)

    validate_create_project_filing_windows(payload)

    project = PatentProject(
        docket_no=payload.docket_no,
        project_mode=payload.project_mode,
        project_stage="final" if payload.project_mode == "final" else "draft",
        in_application_no=payload.in_application_no,
        in_application_date=payload.in_application_date,
        applicant_name=payload.applicant_name,
        applicant_country=payload.applicant_country,
        applicant_address=payload.applicant_address,
        application_title=payload.application_title,
        application_type=payload.application_type,
        provisional_kind=payload.provisional_kind,
        pct_wipo_filed_only=payload.pct_wipo_filed_only,
        attorney_id=payload.attorney_id,
        client_id=payload.client_id,
        client_docket_no=payload.client_docket_no,
    )
    session.add(project)
    session.flush()

    for inventor in payload.inventors:
        session.add(
            PatentInventor(
                project_id=project.id,
                name=inventor.name,
                nationality=inventor.nationality,
                address=inventor.address,
            )
        )

    _persist_priorities_and_international(session, project.id, payload)
    _seed_application_filed_if_final(session, project)

    session.commit()
    session.refresh(project)
    return _project_to_response(session, project)


def list_projects(session: Session) -> list[dict]:
    projects = session.exec(select(PatentProject).order_by(PatentProject.id.desc())).all()
    return [_project_to_response(session, project) for project in projects]


def get_project(session: Session, project_id: int) -> dict | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    return _project_to_response(session, project)


def convert_draft_to_final(session: Session, project_id: int, payload: PatentDraftFinalizeRequest) -> dict | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    parse_in_application_number(payload.in_application_no)
    project.in_application_no = payload.in_application_no
    project.in_application_date = payload.in_application_date
    project.project_stage = "final"
    project.project_mode = "final"
    project.modified_date = datetime.utcnow()
    session.add(project)
    session.flush()
    _seed_application_filed_if_final(session, project)
    session.commit()
    session.refresh(project)
    return _project_to_response(session, project)


def update_project(session: Session, project_id: int, payload: PatentProjectUpdate) -> dict | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None

    if payload.docket_no != project.docket_no:
        existing = session.exec(
            select(PatentProject).where(PatentProject.docket_no == payload.docket_no)
        ).first()
        if existing and existing.id != project_id:
            raise ValueError("Docket number already exists")

    if payload.in_application_no:
        parse_in_application_number(payload.in_application_no)
        if payload.in_application_no != project.in_application_no:
            duplicate = session.exec(
                select(PatentProject).where(PatentProject.in_application_no == payload.in_application_no)
            ).first()
            if duplicate and duplicate.id != project_id:
                raise ValueError("IN application number already exists")

    project.docket_no = payload.docket_no
    project.client_docket_no = payload.client_docket_no
    project.application_title = payload.application_title
    project.in_application_no = payload.in_application_no
    project.in_application_date = payload.in_application_date
    project.applicant_name = payload.applicant_name
    project.applicant_country = payload.applicant_country
    project.applicant_address = payload.applicant_address
    project.attorney_id = payload.attorney_id
    project.modified_date = datetime.utcnow()
    session.add(project)
    session.flush()

    if payload.in_application_date:
        filed_event = session.exec(
            select(PatentStatusEvent).where(
                PatentStatusEvent.project_id == project_id,
                PatentStatusEvent.status_id == STATUS_ID_APPLICATION_FILED,
            )
        ).first()
        if filed_event:
            filed_event.status_date = payload.in_application_date
            session.add(filed_event)

    session.commit()
    session.refresh(project)
    return _project_to_response(session, project)


def update_project_detail(
    session: Session, project_id: int, detail_update: PatentProjectDetailUpdate
) -> dict | None:
    updated = update_project(session, project_id, detail_update.application)
    if not updated:
        return None

    project = session.get(PatentProject, project_id)
    if not project:
        return None

    incoming_status_ids = {item.status_id for item in detail_update.timeline_updates}
    for status_id in incoming_status_ids:
        if status_id not in ALL_STATUS_IDS:
            raise ValueError(f"Invalid status id: {status_id}")

    priorities = session.exec(
        select(PatentPriority).where(PatentPriority.project_id == project_id)
    ).all()
    validate_timeline_updates(
        [(item.status_id, item.status_date) for item in detail_update.timeline_updates],
        requires_non_provisional=project.provisional_kind == "OP",
        in_application_date=project.in_application_date,
        priority_dates=[p.priority_application_date for p in priorities],
    )

    existing_events = session.exec(
        select(PatentStatusEvent).where(PatentStatusEvent.project_id == project_id)
    ).all()

    latest_by_status_id: dict[int, PatentStatusEvent] = {}
    for event in existing_events:
        if event.status_id not in incoming_status_ids:
            session.delete(event)
            continue
        if event.status_id in latest_by_status_id:
            session.delete(event)
            continue
        latest_by_status_id[event.status_id] = event

    for item in detail_update.timeline_updates:
        db_event = latest_by_status_id.get(item.status_id)
        if db_event:
            db_event.status_date = item.status_date
        else:
            session.add(
                PatentStatusEvent(
                    project_id=project_id,
                    status_id=item.status_id,
                    status_date=item.status_date,
                )
            )

    project.modified_date = datetime.utcnow()
    session.add(project)
    session.commit()
    return _project_to_response(session, project)


def update_status_event(session: Session, project_id: int, status_id: int, status_date) -> dict | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None

    events = session.exec(
        select(PatentStatusEvent).where(PatentStatusEvent.project_id == project_id)
    ).all()
    filled = {event.status_id: event.status_date for event in events}
    filled[status_id] = status_date
    priorities = session.exec(
        select(PatentPriority).where(PatentPriority.project_id == project_id)
    ).all()
    validate_timeline_updates(
        sorted(filled.items(), key=lambda item: item[0]),
        requires_non_provisional=project.provisional_kind == "OP",
        in_application_date=project.in_application_date,
        priority_dates=[p.priority_application_date for p in priorities],
    )

    existing = session.exec(
        select(PatentStatusEvent).where(
            PatentStatusEvent.project_id == project_id,
            PatentStatusEvent.status_id == status_id,
        )
    ).first()
    if existing:
        existing.status_date = status_date
        session.add(existing)
    else:
        session.add(PatentStatusEvent(project_id=project_id, status_id=status_id, status_date=status_date))
    session.commit()
    return _project_to_response(session, project)


def list_patent_clients(session: Session) -> list[dict]:
    clients = session.exec(select(PatentClient).order_by(PatentClient.name.asc())).all()
    out: list[dict] = []
    for client in clients:
        out.append(
            {
                "id": client.id,
                "client_code": client.client_code,
                "name": client.name,
                "address": client.address,
                "email": client.email,
                "key_contacts": json.loads(client.key_contacts or "[]"),
                "docketing_email": client.docketing_email,
            }
        )
    return out


def create_patent_client(session: Session, payload: PatentClientInput) -> dict:
    existing = session.exec(
        select(PatentClient).where(PatentClient.client_code == payload.client_code.upper())
    ).first()
    if existing:
        raise ValueError("Client code already exists")
    client = PatentClient(
        client_code=payload.client_code.upper(),
        name=payload.name,
        address=payload.address,
        email=payload.email,
        key_contacts=json.dumps(payload.key_contacts),
        docketing_email=payload.docketing_email,
    )
    session.add(client)
    session.commit()
    session.refresh(client)
    return {
        "id": client.id,
        "client_code": client.client_code,
        "name": client.name,
        "address": client.address,
        "email": client.email,
        "key_contacts": payload.key_contacts,
        "docketing_email": client.docketing_email,
    }


def list_patent_agents(session: Session) -> list[PatentAgent]:
    return session.exec(select(PatentAgent).order_by(PatentAgent.name.asc())).all()


def create_patent_agent(session: Session, payload: PatentAgentInput) -> PatentAgent:
    existing = session.exec(select(PatentAgent).where(PatentAgent.agent_code == payload.agent_code)).first()
    if existing:
        raise ValueError("Patent agent code already exists")
    agent = PatentAgent(**payload.model_dump())
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent
