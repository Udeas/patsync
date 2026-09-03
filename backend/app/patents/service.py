from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .models import (
    PatentAnnuityPayment,
    PatentAnnuityPaymentYear,
    PatentApplicant,
    PatentAgent,
    PatentClient,
    PatentCustomEvent,
    PatentDocketEntry,
    PatentInternationalApplication,
    PatentInventor,
    PatentPriority,
    PatentProject,
    PatentProjectNote,
    PatentStatusEvent,
)
from .patent_status_catalog import STATUS_ID_APPLICATION_FILED, STATUS_ID_ABANDONED, STATUS_ID_FER_ISSUED, STATUS_ID_GRANTED, status_label
from . import docket as docket_rules
from .reminders import compute_next_patent_action
from .patent_status_catalog import ALL_STATUS_IDS
from app.audit.service import record_status_change, write_audit
from app.audit.context import mark_explicit
from app.domain.custom_events import REMINDER_OPTION_NONE, compute_reminder_date, format_short_date
from . import annuity
from .schemas import (
    PatentAgentInput,
    PatentAgentUpdate,
    PatentAnnuityPaymentInput,
    PatentAnnuityPaymentRead,
    PatentAnnuityScheduleRow,
    PatentAnnuitySummary,
    PatentAnnuityTransferInput,
    PatentClientInput,
    PatentClientUpdate,
    PatentCustomEventClose,
    PatentCustomEventCreate,
    PatentCustomEventRead,
    PatentDocketEntryClose,
    PatentDocketEntryRead,
    PatentDraftFinalizeRequest,
    PatentInternationalInput,
    PatentPriorityInput,
    PatentProjectCreate,
    PatentProjectDetailUpdate,
    PatentProjectNoteInput,
    PatentProjectNoteRead,
    PatentProjectUpdate,
)
from .validators import (
    DIVISIONAL_APPLICATION_TYPES,
    PATENT_OF_ADDITION_APPLICATION_TYPES,
    parse_in_application_number,
    validate_create_project_filing_windows,
    validate_divisional_parent_application,
)
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


def _agent_summary(agent: PatentAgent) -> dict:
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


def _client_summary(patent_client: PatentClient) -> dict:
    return {
        "id": patent_client.id,
        "client_code": patent_client.client_code,
        "name": patent_client.name,
    }


def _shape_relations(
    applicants,
    inventors,
    priorities,
    international_apps,
    status_events,
    attorney,
    client,
) -> dict:
    return {
        "applicants": [
            {
                "name": applicant.name,
                "country": applicant.country,
                "address": applicant.address,
            }
            for applicant in applicants
        ],
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


def _agent_to_dict(agent: PatentAgent | None) -> dict | None:
    if not agent:
        return None
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


def _client_to_dict(patent_client: PatentClient | None) -> dict | None:
    if not patent_client:
        return None
    return {
        "id": patent_client.id,
        "client_code": patent_client.client_code,
        "name": patent_client.name,
    }


def _build_relations_dict(
    *,
    applicants,
    inventors,
    priorities,
    international_apps,
    status_events,
    attorney,
    client,
    parent_docket_no=None,
    parent_client_docket_no=None,
    parent_priority_dates=(),
    annuity_paid_years=(),
    notes=(),
    custom_events=(),
    docket_entries=(),
) -> dict:
    return {
        "notes": [
            {"id": n.id, "note_text": n.note_text, "created_date": n.created_date}
            for n in notes
        ],
        "custom_events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "event_date": e.event_date,
                "reminder_option": e.reminder_option,
                "reminder_date": e.reminder_date,
                "closure_date": e.closure_date,
                "created_date": e.created_date,
            }
            for e in custom_events
        ],
        "custom_event_reminders": [
            {
                "kind": "custom_event",
                "fire_on": e.reminder_date,
                "label": f"{e.event_type} issued on {format_short_date(e.event_date)}",
            }
            for e in custom_events
            if e.closure_date is None and e.reminder_date is not None
        ],
        "docket_entries": [
            {
                "id": e.id,
                "item_type": e.item_type,
                "title": e.title,
                "rule_reference": e.rule_reference,
                "due_date": e.due_date,
                "is_internal_target": e.is_internal_target,
                "is_system_generated": e.is_system_generated,
                "auto_satisfied": e.auto_satisfied,
                "closure_date": e.closure_date,
                "created_date": e.created_date,
            }
            for e in docket_entries
        ],
        "docket_entry_reminders": [
            _docket_entry_reminder_row(e) for e in docket_entries if e.closure_date is None
        ],
        "applicants": [
            {"name": applicant.name, "country": applicant.country, "address": applicant.address}
            for applicant in applicants
        ],
        "inventors": [
            {"name": inv.name, "nationality": inv.nationality, "address": inv.address}
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
        "parent_docket_no": parent_docket_no,
        "parent_client_docket_no": parent_client_docket_no,
        "_status_events_raw": status_events,
        "_parent_priority_dates_raw": list(parent_priority_dates),
        "_annuity_paid_years_raw": list(annuity_paid_years),
    }


def _load_project_relations(session: Session, project: PatentProject) -> dict:
    applicants = session.exec(
        select(PatentApplicant)
        .where(PatentApplicant.project_id == project.id)
        .order_by(PatentApplicant.id.asc())
    ).all()
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
    notes = _project_notes(session, project.id)
    custom_events = _patent_custom_events(session, project.id)
    docket_entries = _patent_docket_entries(session, project.id)

    attorney = (
        _agent_to_dict(session.get(PatentAgent, project.attorney_id))
        if project.attorney_id
        else None
    )
    client = (
        _client_to_dict(session.get(PatentClient, project.client_id))
        if project.client_id
        else None
    )

    parent_docket_no = None
    parent_client_docket_no = None
    parent_priority_dates: list = []
    if project.parent_project_id:
        parent = session.get(PatentProject, project.parent_project_id)
        if parent:
            parent_docket_no = parent.docket_no
            parent_client_docket_no = parent.client_docket_no
            parent_priority_dates = _parent_priority_dates(session, project)

    return _build_relations_dict(
        applicants=applicants,
        inventors=inventors,
        priorities=priorities,
        international_apps=international_apps,
        status_events=status_events,
        attorney=attorney,
        client=client,
        parent_docket_no=parent_docket_no,
        parent_client_docket_no=parent_client_docket_no,
        parent_priority_dates=parent_priority_dates,
        annuity_paid_years=_annuity_paid_years(session, project.id),
        notes=notes,
        custom_events=custom_events,
        docket_entries=docket_entries,
    )


def _project_notes(session: Session, project_id: int) -> list[PatentProjectNote]:
    return session.exec(
        select(PatentProjectNote)
        .where(PatentProjectNote.project_id == project_id)
        .order_by(PatentProjectNote.created_date.desc(), PatentProjectNote.id.desc())
    ).all()


def add_project_note(
    session: Session, project_id: int, payload: PatentProjectNoteInput
) -> list[PatentProjectNoteRead] | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    note_text = payload.note_text.strip()
    if not note_text:
        raise ValueError("Note text is required")
    session.add(PatentProjectNote(project_id=project_id, note_text=note_text))
    session.commit()
    return [
        PatentProjectNoteRead(id=n.id, note_text=n.note_text, created_date=n.created_date)
        for n in _project_notes(session, project_id)
    ]


def update_project_note(
    session: Session, project_id: int, note_id: int, payload: PatentProjectNoteInput
) -> list[PatentProjectNoteRead] | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    note = session.get(PatentProjectNote, note_id)
    if not note or note.project_id != project_id:
        return None
    note_text = payload.note_text.strip()
    if not note_text:
        raise ValueError("Note text is required")
    note.note_text = note_text
    session.add(note)
    session.commit()
    return [
        PatentProjectNoteRead(id=n.id, note_text=n.note_text, created_date=n.created_date)
        for n in _project_notes(session, project_id)
    ]


def _patent_custom_events(session: Session, project_id: int) -> list[PatentCustomEvent]:
    return session.exec(
        select(PatentCustomEvent)
        .where(PatentCustomEvent.project_id == project_id)
        .order_by(PatentCustomEvent.event_date.desc(), PatentCustomEvent.id.desc())
    ).all()


def _patent_custom_events_read(session: Session, project_id: int) -> list[PatentCustomEventRead]:
    return [
        PatentCustomEventRead(
            id=e.id,
            event_type=e.event_type,
            event_date=e.event_date,
            reminder_option=e.reminder_option,
            reminder_date=e.reminder_date,
            closure_date=e.closure_date,
            created_date=e.created_date,
        )
        for e in _patent_custom_events(session, project_id)
    ]


def add_patent_custom_event(
    session: Session, project_id: int, payload: PatentCustomEventCreate
) -> list[PatentCustomEventRead] | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    reminder_date = compute_reminder_date(payload.event_date, payload.reminder_option)
    session.add(
        PatentCustomEvent(
            project_id=project_id,
            event_type=payload.event_type.strip(),
            event_date=payload.event_date,
            reminder_option=payload.reminder_option,
            reminder_date=reminder_date,
        )
    )
    session.commit()
    return _patent_custom_events_read(session, project_id)


def close_patent_custom_event(
    session: Session, project_id: int, event_id: int, payload: PatentCustomEventClose
) -> list[PatentCustomEventRead] | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    event = session.get(PatentCustomEvent, event_id)
    if not event or event.project_id != project_id:
        return None
    if event.closure_date is not None:
        raise ValueError("Event is already closed")
    event.closure_date = payload.closure_date
    session.add(event)
    session.commit()
    return _patent_custom_events_read(session, project_id)


def delete_patent_custom_event(
    session: Session, project_id: int, event_id: int
) -> list[PatentCustomEventRead] | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    event = session.get(PatentCustomEvent, event_id)
    if not event or event.project_id != project_id:
        return None
    if event.reminder_option != REMINDER_OPTION_NONE or event.closure_date is not None:
        raise ValueError("Only open, no-reminder events can be deleted")
    session.delete(event)
    session.commit()
    return _patent_custom_events_read(session, project_id)


def _patent_docket_entries(session: Session, project_id: int) -> list[PatentDocketEntry]:
    return session.exec(
        select(PatentDocketEntry)
        .where(PatentDocketEntry.project_id == project_id)
        .order_by(PatentDocketEntry.due_date.asc(), PatentDocketEntry.id.asc())
    ).all()


def _patent_docket_entry_read(e: PatentDocketEntry) -> PatentDocketEntryRead:
    return PatentDocketEntryRead(
        id=e.id,
        item_type=e.item_type,
        title=e.title,
        rule_reference=e.rule_reference,
        due_date=e.due_date,
        is_internal_target=e.is_internal_target,
        is_system_generated=e.is_system_generated,
        auto_satisfied=e.auto_satisfied,
        closure_date=e.closure_date,
        created_date=e.created_date,
    )


def _patent_docket_entries_read(session: Session, project_id: int) -> list[PatentDocketEntryRead]:
    return [_patent_docket_entry_read(e) for e in _patent_docket_entries(session, project_id)]


def _generate_default_docket_entries(
    session: Session, project: PatentProject, *, has_priority_claim: bool
) -> None:
    """Requirement 1 of the auto-docket feature: create the default Indian
    filing-formality items once, at project creation. Idempotent by design
    (only ever called once, on a freshly-flushed project with no existing
    docket entries) and additionally protected by the DB unique constraint
    on (project_id, item_type)."""
    plans = docket_rules.plan_default_docket_entries(
        application_type=project.application_type,
        filing_date=project.in_application_date,
        has_priority_claim=has_priority_claim,
        proof_of_right_furnished=project.proof_of_right_furnished,
    )
    now = datetime.utcnow()
    for plan in plans:
        session.add(
            PatentDocketEntry(
                project_id=project.id,
                item_type=plan.item_type,
                title=plan.title,
                rule_reference=plan.rule_reference,
                due_date=plan.due_date,
                is_internal_target=plan.is_internal_target,
                is_system_generated=True,
                auto_satisfied=plan.auto_satisfied,
                closure_date=now.date() if plan.auto_satisfied else None,
            )
        )
    if plans:
        write_audit(
            session,
            action="docket_entries_generated",
            entity_type="patent",
            entity_id=project.id,
            entity_label=project.docket_no,
            changes=[{"field": "docket_entries", "old": None, "new": [p.item_type for p in plans]}],
        )


def upsert_form3_updated_entry(session: Session, project_id: int, fer_date) -> None:
    """Requirement 2: whenever the FER date is entered or updated, create
    (or update in place - never duplicate) the Rule 12(2) updated-Form-3
    item due 3 months after that date."""
    if not fer_date:
        return
    plan = docket_rules.plan_form3_updated_entry(fer_date)
    existing = session.exec(
        select(PatentDocketEntry).where(
            PatentDocketEntry.project_id == project_id,
            PatentDocketEntry.item_type == plan.item_type,
        )
    ).first()
    if existing:
        if (
            existing.due_date == plan.due_date
            and existing.title == plan.title
            and existing.rule_reference == plan.rule_reference
        ):
            return
        existing.due_date = plan.due_date
        existing.title = plan.title
        existing.rule_reference = plan.rule_reference
        session.add(existing)
        write_audit(
            session,
            action="docket_entry_updated",
            entity_type="patent",
            entity_id=project_id,
            entity_label=plan.title,
            changes=[{"field": "due_date", "old": None, "new": plan.due_date.isoformat()}],
        )
    else:
        session.add(
            PatentDocketEntry(
                project_id=project_id,
                item_type=plan.item_type,
                title=plan.title,
                rule_reference=plan.rule_reference,
                due_date=plan.due_date,
                is_system_generated=True,
            )
        )
        write_audit(
            session,
            action="docket_entry_generated",
            entity_type="patent",
            entity_id=project_id,
            entity_label=plan.title,
            changes=[{"field": "due_date", "old": None, "new": plan.due_date.isoformat()}],
        )


def upsert_form27_entry(session: Session, project_id: int, grant_date, grant_number: str | None) -> None:
    """Triggered whenever the grant date is entered or corrected. Each Form
    27 cycle is its own row (item_type keyed by the reporting block's start
    FY), so "correcting the grant date" means finding whichever cycle is
    currently open (unclosed) for this project and either updating it in
    place (grant date correction lands in the same block) or replacing it
    (correction shifts to a different block) - never leaving a stale
    duplicate and never touching already-closed historical cycles."""
    if not grant_date or not (grant_number or "").strip():
        return
    plan = docket_rules.plan_form27_first_entry(grant_date=grant_date, grant_number=grant_number.strip())

    open_entries = session.exec(
        select(PatentDocketEntry).where(
            PatentDocketEntry.project_id == project_id,
            PatentDocketEntry.item_type.like(f"{docket_rules.ITEM_FORM27_PREFIX}%"),
            PatentDocketEntry.closure_date.is_(None),
        )
    ).all()

    existing = next((e for e in open_entries if e.item_type == plan.item_type), None)
    if existing:
        if existing.due_date != plan.due_date or existing.title != plan.title:
            existing.due_date = plan.due_date
            existing.title = plan.title
            session.add(existing)
            write_audit(
                session,
                action="docket_entry_updated",
                entity_type="patent",
                entity_id=project_id,
                entity_label=plan.title,
                changes=[{"field": "due_date", "old": None, "new": plan.due_date.isoformat()}],
            )
        return

    # No open cycle matches the newly computed block - the grant date
    # correction moved to a different FY block. Replace any other open
    # Form 27 cycle (there should be at most one) rather than stacking up.
    for stale in open_entries:
        session.delete(stale)

    session.add(
        PatentDocketEntry(
            project_id=project_id,
            item_type=plan.item_type,
            title=plan.title,
            rule_reference=plan.rule_reference,
            due_date=plan.due_date,
            is_system_generated=True,
        )
    )
    write_audit(
        session,
        action="docket_entry_generated",
        entity_type="patent",
        entity_id=project_id,
        entity_label=plan.title,
        changes=[{"field": "due_date", "old": None, "new": plan.due_date.isoformat()}],
    )


def close_patent_docket_entry(
    session: Session, project_id: int, entry_id: int, payload: PatentDocketEntryClose
) -> list[PatentDocketEntryRead] | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    entry = session.get(PatentDocketEntry, entry_id)
    if not entry or entry.project_id != project_id:
        return None
    if entry.closure_date is not None:
        raise ValueError("Docket entry is already closed")
    entry.closure_date = payload.closure_date
    session.add(entry)

    # Form 27 roll-forward: closing one cycle generates the next one, as
    # long as the patent is still tracked as in force. There is no
    # dedicated in-force/lapsed/revoked status in this codebase - is_archived
    # is the closest existing proxy for "stop tracking this patent" and is
    # used here as a practical gate, not a legal lapse determination.
    block_start = docket_rules.parse_form27_block_start(entry.item_type)
    if block_start is not None and not project.is_archived:
        next_plan = docket_rules.plan_form27_next_entry(
            grant_number=project.grant_number or "",
            prior_block_start_year=block_start,
            prior_due_date=entry.due_date,
        )
        session.add(
            PatentDocketEntry(
                project_id=project_id,
                item_type=next_plan.item_type,
                title=next_plan.title,
                rule_reference=next_plan.rule_reference,
                due_date=next_plan.due_date,
                is_system_generated=True,
            )
        )
        write_audit(
            session,
            action="docket_entry_generated",
            entity_type="patent",
            entity_id=project_id,
            entity_label=next_plan.title,
            changes=[{"field": "due_date", "old": None, "new": next_plan.due_date.isoformat()}],
        )

    session.commit()
    return _patent_docket_entries_read(session, project_id)


def _docket_entry_reminder_row(e: PatentDocketEntry) -> dict:
    return {
        "kind": "docket_entry",
        "fire_on": e.due_date,
        "label": f"{e.title} ({e.rule_reference})",
    }


def _annuity_paid_years(session: Session, project_id: int) -> list[int]:
    payment_ids = session.exec(
        select(PatentAnnuityPayment.id).where(PatentAnnuityPayment.project_id == project_id)
    ).all()
    if not payment_ids:
        return []
    rows = session.exec(
        select(PatentAnnuityPaymentYear).where(PatentAnnuityPaymentYear.payment_id.in_(payment_ids))
    ).all()
    return [row.renewal_year for row in rows]


def _assemble_response(project: PatentProject, relations: dict) -> dict:
    relations = dict(relations)
    status_events_raw = relations.pop("_status_events_raw")
    parent_priority_dates_raw = relations.pop("_parent_priority_dates_raw", [])
    annuity_paid_years_raw = relations.pop("_annuity_paid_years_raw", [])
    filled_status = {event.status_id: event.status_date for event in status_events_raw}
    current_status = derive_current_status(filled_status)
    priority_dates = [
        p["priority_application_date"] for p in relations["priorities"]
    ]
    grant_date = filled_status.get(STATUS_ID_GRANTED)
    next_action = compute_next_patent_action(
        filled=filled_status,
        current_status_id=current_status[0] if current_status else None,
        in_application_date=project.in_application_date,
        priority_dates=priority_dates,
        provisional_kind=project.provisional_kind,
        application_type=project.application_type,
        parent_application_date=project.parent_application_date,
        parent_priority_dates=parent_priority_dates_raw,
        grant_date=grant_date,
        annuity_paid_years=annuity_paid_years_raw,
        is_annuity_transferred=project.annuity_transferred_at is not None,
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
        "parent_project_id": project.parent_project_id,
        "parent_application_no": project.parent_application_no,
        "parent_application_date": project.parent_application_date,
        "parent_priority_dates": parent_priority_dates_raw,
        "grant_number": project.grant_number,
        "annuity_paid_upto": project.annuity_paid_upto,
        "next_annuity_due": project.next_annuity_due,
        "is_annuity_transferred": project.annuity_transferred_at is not None,
        "is_archived": project.is_archived,
        "client_docket_no": project.client_docket_no,
        "abandon_reason": project.abandon_reason,
        "current_status_id": current_status[0] if current_status else None,
        "current_status_date": current_status[1] if current_status else None,
        "due_action": due_action,
        "action_due_date": action_due_date,
        **relations,
    }


def _project_to_response(session: Session, project: PatentProject) -> dict:
    return _assemble_response(project, _load_project_relations(session, project))


def _parent_priority_dates(session: Session, project: PatentProject) -> list:
    if not project.parent_project_id:
        return []
    return [
        p.priority_application_date
        for p in session.exec(
            select(PatentPriority).where(PatentPriority.project_id == project.parent_project_id)
        ).all()
    ]


def _validate_in_number_date_year_match(in_application_no: str | None, in_application_date) -> None:
    if not in_application_no or not in_application_date:
        return
    parsed = parse_in_application_number(in_application_no)
    if parsed.filing_year != in_application_date.year:
        raise ValueError(
            "IN application number year does not match IN application date year. "
            "Please check either application number or date."
        )


def _is_complete_applicant(applicant) -> bool:
    name = str(getattr(applicant, "name", "") or "").strip()
    country = str(getattr(applicant, "country", "") or "").strip()
    address = str(getattr(applicant, "address", "") or "").strip()
    return bool(name and country and address)


def _is_complete_inventor(inventor) -> bool:
    name = str(getattr(inventor, "name", "") or "").strip()
    country = str(getattr(inventor, "nationality", "") or "").strip()
    address = str(getattr(inventor, "address", "") or "").strip()
    return bool(name and country and address)


def _validate_final_mode_contacts(*, project_mode: str, applicants: list, inventors: list) -> None:
    if project_mode != "final":
        return
    if not any(_is_complete_applicant(applicant) for applicant in applicants):
        raise ValueError(
            "For Final Docket, at least one applicant with name, country, and address is required."
        )
    if not any(_is_complete_inventor(inventor) for inventor in inventors):
        raise ValueError(
            "For Final Docket, at least one inventor with name, country, and address is required."
        )


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
    if (payload.application_type or "").strip() not in DIVISIONAL_APPLICATION_TYPES:
        _validate_in_number_date_year_match(payload.in_application_no, payload.in_application_date)

    validate_create_project_filing_windows(payload)
    validate_divisional_parent_application(payload)

    source_applicants = payload.applicants
    if not source_applicants:
        from .schemas import PatentApplicantInput

        source_applicants = [
            PatentApplicantInput(
                name=payload.applicant_name,
                country=payload.applicant_country,
                address=payload.applicant_address,
            )
        ]
    primary_applicant = source_applicants[0]
    _validate_final_mode_contacts(
        project_mode=payload.project_mode,
        applicants=list(source_applicants),
        inventors=list(payload.inventors),
    )

    project = PatentProject(
        docket_no=payload.docket_no,
        project_mode=payload.project_mode,
        project_stage="final" if payload.project_mode == "final" else "draft",
        in_application_no=payload.in_application_no,
        in_application_date=payload.in_application_date,
        applicant_name=(primary_applicant.name or "").strip(),
        applicant_country=((primary_applicant.country or "").strip() or None),
        applicant_address=((primary_applicant.address or "").strip() or None),
        application_title=payload.application_title,
        application_type=payload.application_type,
        provisional_kind=payload.provisional_kind,
        pct_wipo_filed_only=payload.pct_wipo_filed_only,
        proof_of_right_furnished=payload.proof_of_right_furnished,
        attorney_id=payload.attorney_id,
        client_id=payload.client_id,
        client_docket_no=payload.client_docket_no,
        parent_project_id=payload.parent_project_id,
        parent_application_no=payload.parent_application_no,
        parent_application_date=payload.parent_application_date,
        grant_number=payload.grant_number,
        annuity_paid_upto=payload.annuity_paid_upto,
        next_annuity_due=payload.next_annuity_due,
    )
    session.add(project)
    session.flush()

    for applicant in source_applicants:
        name = str(applicant.name or "").strip()
        country = str(applicant.country or "").strip() or None
        address = str(applicant.address or "").strip() or None
        if not name and not country and not address:
            continue
        session.add(
            PatentApplicant(
                project_id=project.id,
                name=name,
                country=country,
                address=address,
            )
        )

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
    _generate_default_docket_entries(
        session, project, has_priority_claim=len(payload.priorities) > 0
    )

    session.commit()
    session.refresh(project)
    return _project_to_response(session, project)


def _load_relations_bulk(
    session: Session, projects: list[PatentProject]
) -> dict[int, dict]:
    """Load every project's relations in a fixed number of queries (no N+1)."""
    project_ids = [project.id for project in projects]

    def _grouped(rows) -> dict[int, list]:
        grouped: dict[int, list] = defaultdict(list)
        for row in rows:
            grouped[row.project_id].append(row)
        return grouped

    applicants_by = _grouped(
        session.exec(
            select(PatentApplicant)
            .where(PatentApplicant.project_id.in_(project_ids))
            .order_by(PatentApplicant.project_id.asc(), PatentApplicant.id.asc())
        ).all()
    )
    inventors_by = _grouped(
        session.exec(
            select(PatentInventor)
            .where(PatentInventor.project_id.in_(project_ids))
            .order_by(PatentInventor.project_id.asc(), PatentInventor.id.asc())
        ).all()
    )
    priorities_by = _grouped(
        session.exec(
            select(PatentPriority)
            .where(PatentPriority.project_id.in_(project_ids))
            .order_by(
                PatentPriority.project_id.asc(),
                PatentPriority.priority_application_date.asc(),
                PatentPriority.id.asc(),
            )
        ).all()
    )
    international_by = _grouped(
        session.exec(
            select(PatentInternationalApplication)
            .where(PatentInternationalApplication.project_id.in_(project_ids))
            .order_by(
                PatentInternationalApplication.project_id.asc(),
                PatentInternationalApplication.international_application_date.asc(),
                PatentInternationalApplication.id.asc(),
            )
        ).all()
    )
    status_events_by = _grouped(
        session.exec(
            select(PatentStatusEvent)
            .where(PatentStatusEvent.project_id.in_(project_ids))
            .order_by(
                PatentStatusEvent.project_id.asc(),
                PatentStatusEvent.status_date.asc(),
                PatentStatusEvent.status_id.asc(),
            )
        ).all()
    )
    custom_events_by = _grouped(
        session.exec(
            select(PatentCustomEvent)
            .where(PatentCustomEvent.project_id.in_(project_ids))
            .order_by(PatentCustomEvent.project_id.asc(), PatentCustomEvent.event_date.desc())
        ).all()
    )
    docket_entries_by = _grouped(
        session.exec(
            select(PatentDocketEntry)
            .where(PatentDocketEntry.project_id.in_(project_ids))
            .order_by(PatentDocketEntry.project_id.asc(), PatentDocketEntry.due_date.asc())
        ).all()
    )

    parent_ids = {project.parent_project_id for project in projects if project.parent_project_id}
    parents_by_id: dict[int, PatentProject] = {}
    if parent_ids:
        for parent in session.exec(
            select(PatentProject).where(PatentProject.id.in_(parent_ids))
        ).all():
            parents_by_id[parent.id] = parent

    parent_priorities_by = _grouped(
        session.exec(
            select(PatentPriority).where(PatentPriority.project_id.in_(parent_ids))
        ).all()
        if parent_ids
        else []
    )

    attorney_ids = {project.attorney_id for project in projects if project.attorney_id}
    agents_by_id: dict[int, dict | None] = {}
    if attorney_ids:
        for agent in session.exec(
            select(PatentAgent).where(PatentAgent.id.in_(attorney_ids))
        ).all():
            agents_by_id[agent.id] = _agent_to_dict(agent)

    client_ids = {project.client_id for project in projects if project.client_id}
    clients_by_id: dict[int, dict | None] = {}
    if client_ids:
        for patent_client in session.exec(
            select(PatentClient).where(PatentClient.id.in_(client_ids))
        ).all():
            clients_by_id[patent_client.id] = _client_to_dict(patent_client)

    annuity_payments_by = _grouped(
        session.exec(
            select(PatentAnnuityPayment).where(PatentAnnuityPayment.project_id.in_(project_ids))
        ).all()
    )
    all_payment_ids = [payment.id for payments in annuity_payments_by.values() for payment in payments]
    annuity_payment_years_by_payment: dict[int, list[int]] = defaultdict(list)
    if all_payment_ids:
        for row in session.exec(
            select(PatentAnnuityPaymentYear).where(PatentAnnuityPaymentYear.payment_id.in_(all_payment_ids))
        ).all():
            annuity_payment_years_by_payment[row.payment_id].append(row.renewal_year)
    annuity_paid_years_by_project: dict[int, list[int]] = {}
    for project_id, payments in annuity_payments_by.items():
        years: list[int] = []
        for payment in payments:
            years.extend(annuity_payment_years_by_payment.get(payment.id, []))
        annuity_paid_years_by_project[project_id] = years

    relations_by_project: dict[int, dict] = {}
    for project in projects:
        parent = parents_by_id.get(project.parent_project_id) if project.parent_project_id else None
        relations_by_project[project.id] = _build_relations_dict(
            applicants=applicants_by.get(project.id, []),
            inventors=inventors_by.get(project.id, []),
            priorities=priorities_by.get(project.id, []),
            international_apps=international_by.get(project.id, []),
            status_events=status_events_by.get(project.id, []),
            attorney=agents_by_id.get(project.attorney_id) if project.attorney_id else None,
            client=clients_by_id.get(project.client_id) if project.client_id else None,
            annuity_paid_years=annuity_paid_years_by_project.get(project.id, []),
            parent_docket_no=parent.docket_no if parent else None,
            parent_client_docket_no=parent.client_docket_no if parent else None,
            parent_priority_dates=(
                [p.priority_application_date for p in parent_priorities_by.get(parent.id, [])]
                if parent
                else []
            ),
            custom_events=custom_events_by.get(project.id, []),
            docket_entries=docket_entries_by.get(project.id, []),
        )
    return relations_by_project


def list_projects(session: Session, include_archived: bool = False) -> list[dict]:
    query = select(PatentProject)
    if not include_archived:
        query = query.where(PatentProject.is_archived.is_(False))
    projects = session.exec(query.order_by(PatentProject.id.desc())).all()
    if not projects:
        return []
    relations_by_project = _load_relations_bulk(session, projects)
    return [
        _assemble_response(project, relations_by_project[project.id])
        for project in projects
    ]


def get_project(session: Session, project_id: int) -> dict | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    return _project_to_response(session, project)


def archive_project(session: Session, project_id: int) -> dict | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    project.is_archived = True
    project.modified_date = datetime.utcnow()
    session.add(project)
    session.commit()
    session.refresh(project)
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

    if payload.project_mode == "final" and not payload.in_application_no:
        raise ValueError("IN application number is required for final projects")
    if payload.project_mode == "final" and not payload.in_application_date:
        raise ValueError("IN application date is required for final projects")
    effective_application_type = (payload.application_type or project.application_type or "").strip()
    if effective_application_type not in DIVISIONAL_APPLICATION_TYPES:
        _validate_in_number_date_year_match(payload.in_application_no, payload.in_application_date)

    existing_applicants = session.exec(
        select(PatentApplicant).where(PatentApplicant.project_id == project_id)
    ).all()
    existing_inventors = session.exec(
        select(PatentInventor).where(PatentInventor.project_id == project_id)
    ).all()
    existing_priorities = session.exec(
        select(PatentPriority).where(PatentPriority.project_id == project_id)
    ).all()
    existing_international = session.exec(
        select(PatentInternationalApplication).where(PatentInternationalApplication.project_id == project_id)
    ).all()
    effective_mode = payload.project_mode or project.project_mode
    effective_applicants = list(payload.applicants) if payload.applicants is not None else list(existing_applicants)
    effective_inventors = list(payload.inventors) if payload.inventors is not None else list(existing_inventors)
    effective_priorities = (
        list(payload.priorities)
        if payload.priorities is not None
        else [
            PatentPriorityInput(
                priority_application_no=p.priority_application_no,
                priority_application_date=p.priority_application_date,
                country=p.country,
                title=p.title,
            )
            for p in existing_priorities
        ]
    )
    effective_international = (
        list(payload.international_applications)
        if payload.international_applications is not None
        else [
            PatentInternationalInput(
                international_application_no=r.international_application_no,
                international_application_date=r.international_application_date,
            )
            for r in existing_international
        ]
    )
    _validate_final_mode_contacts(
        project_mode=effective_mode,
        applicants=effective_applicants,
        inventors=effective_inventors,
    )
    effective_validation_payload = PatentProjectCreate(
        project_mode=payload.project_mode or project.project_mode,
        application_type=payload.application_type or project.application_type or "",
        docket_no=payload.docket_no,
        in_application_no=payload.in_application_no,
        in_application_date=payload.in_application_date,
        applicant_name=payload.applicant_name,
        applicant_country=payload.applicant_country,
        applicant_address=payload.applicant_address,
        applicants=payload.applicants or [],
        application_title=payload.application_title,
        attorney_id=payload.attorney_id,
        client_id=payload.client_id,
        client_docket_no=payload.client_docket_no,
        provisional_kind=payload.provisional_kind,
        pct_wipo_filed_only=payload.pct_wipo_filed_only if payload.pct_wipo_filed_only is not None else project.pct_wipo_filed_only,
        inventors=payload.inventors or [],
        priorities=effective_priorities,
        international_applications=effective_international,
        parent_project_id=payload.parent_project_id if payload.parent_project_id is not None else project.parent_project_id,
        parent_application_no=payload.parent_application_no if payload.parent_application_no is not None else project.parent_application_no,
        parent_application_date=payload.parent_application_date if payload.parent_application_date is not None else project.parent_application_date,
    )
    validate_create_project_filing_windows(effective_validation_payload)
    validate_divisional_parent_application(effective_validation_payload)

    project.docket_no = payload.docket_no
    if payload.project_mode:
        project.project_mode = payload.project_mode
        project.project_stage = "final" if payload.project_mode == "final" else "draft"
    if payload.application_type is not None:
        project.application_type = payload.application_type
    project.client_docket_no = payload.client_docket_no
    project.application_title = payload.application_title
    project.in_application_no = payload.in_application_no
    project.in_application_date = payload.in_application_date
    project.attorney_id = payload.attorney_id
    if payload.client_id is not None:
        project.client_id = payload.client_id
    if payload.provisional_kind is not None:
        project.provisional_kind = payload.provisional_kind
    if payload.pct_wipo_filed_only is not None:
        project.pct_wipo_filed_only = payload.pct_wipo_filed_only
    if payload.parent_project_id is not None:
        project.parent_project_id = payload.parent_project_id
    if payload.parent_application_no is not None:
        project.parent_application_no = payload.parent_application_no
    if payload.parent_application_date is not None:
        project.parent_application_date = payload.parent_application_date
    if payload.grant_number is not None:
        project.grant_number = payload.grant_number
    if payload.annuity_paid_upto is not None:
        project.annuity_paid_upto = payload.annuity_paid_upto
    if payload.next_annuity_due is not None:
        project.next_annuity_due = payload.next_annuity_due

    if payload.applicants is not None:
        existing_applicants = session.exec(
            select(PatentApplicant).where(PatentApplicant.project_id == project_id)
        ).all()
        for applicant in existing_applicants:
            session.delete(applicant)
        for applicant in payload.applicants:
            name = str(applicant.name or "").strip()
            country = str(applicant.country or "").strip() or None
            address = str(applicant.address or "").strip() or None
            if not name and not country and not address:
                continue
            session.add(
                PatentApplicant(
                    project_id=project_id,
                    name=name,
                    country=country,
                    address=address,
                )
            )
        primary = next(
            (
                applicant
                for applicant in payload.applicants
                if str(applicant.name or "").strip()
                or str(applicant.country or "").strip()
                or str(applicant.address or "").strip()
            ),
            None,
        )
        if primary:
            project.applicant_name = str(primary.name or "").strip()
            project.applicant_country = str(primary.country or "").strip() or None
            project.applicant_address = str(primary.address or "").strip() or None
        else:
            project.applicant_name = ""
            project.applicant_country = None
            project.applicant_address = None
    else:
        project.applicant_name = payload.applicant_name
        project.applicant_country = payload.applicant_country
        project.applicant_address = payload.applicant_address
    project.modified_date = datetime.utcnow()
    session.add(project)
    session.flush()

    if payload.inventors is not None:
        existing_inventors = session.exec(
            select(PatentInventor).where(PatentInventor.project_id == project_id)
        ).all()
        for inventor in existing_inventors:
            session.delete(inventor)
        for inventor in payload.inventors:
            session.add(
                PatentInventor(
                    project_id=project_id,
                    name=inventor.name,
                    nationality=inventor.nationality,
                    address=inventor.address,
                )
            )

    if payload.priorities is not None:
        existing_priorities = session.exec(
            select(PatentPriority).where(PatentPriority.project_id == project_id)
        ).all()
        for priority in existing_priorities:
            session.delete(priority)
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

    if payload.international_applications is not None:
        existing_international = session.exec(
            select(PatentInternationalApplication).where(PatentInternationalApplication.project_id == project_id)
        ).all()
        for row in existing_international:
            session.delete(row)
        for row in payload.international_applications:
            session.add(
                PatentInternationalApplication(
                    project_id=project_id,
                    international_application_no=row.international_application_no,
                    international_application_date=row.international_application_date,
                )
            )

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

    granted_item = next(
        (item for item in detail_update.timeline_updates if item.status_id == STATUS_ID_GRANTED),
        None,
    )
    if granted_item and granted_item.status_date and not (project.grant_number or "").strip():
        raise ValueError("Grant number is required once Grant date is set")

    priorities = session.exec(
        select(PatentPriority).where(PatentPriority.project_id == project_id)
    ).all()
    validate_timeline_updates(
        [(item.status_id, item.status_date) for item in detail_update.timeline_updates],
        requires_non_provisional=project.provisional_kind == "OP",
        in_application_date=project.in_application_date,
        priority_dates=[p.priority_application_date for p in priorities],
        is_divisional=(project.application_type or "").strip() in DIVISIONAL_APPLICATION_TYPES,
        is_patent_of_addition=(project.application_type or "").strip() in PATENT_OF_ADDITION_APPLICATION_TYPES,
        parent_application_date=project.parent_application_date,
        parent_priority_dates=_parent_priority_dates(session, project),
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

    fer_item = next(
        (item for item in detail_update.timeline_updates if item.status_id == STATUS_ID_FER_ISSUED),
        None,
    )
    if fer_item and fer_item.status_date:
        upsert_form3_updated_entry(session, project_id, fer_item.status_date)

    if granted_item and granted_item.status_date:
        upsert_form27_entry(session, project_id, granted_item.status_date, project.grant_number)

    project.modified_date = datetime.utcnow()
    session.add(project)
    session.commit()
    return _project_to_response(session, project)


def update_status_event(session: Session, project_id: int, status_id: int, status_date, abandon_reason: str | None = None) -> dict | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None

    # Pre-mark explicit BEFORE any query that may auto-flush the dirty project
    mark_explicit(session, "patent", project_id)

    if status_id == STATUS_ID_ABANDONED:
        reason = (abandon_reason or "").strip()
        if not reason:
            raise ValueError("Abandon reason is required.")
        project.abandon_reason = reason

    if status_id == STATUS_ID_GRANTED and status_date and not (project.grant_number or "").strip():
        raise ValueError("Grant number is required once Grant date is set")

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
        is_divisional=(project.application_type or "").strip() in DIVISIONAL_APPLICATION_TYPES,
        is_patent_of_addition=(project.application_type or "").strip() in PATENT_OF_ADDITION_APPLICATION_TYPES,
        parent_application_date=project.parent_application_date,
        parent_priority_dates=_parent_priority_dates(session, project),
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
    old_status = derive_current_status({e.status_id: e.status_date for e in events})
    old_label = status_label(old_status[0]) if old_status else None
    extra = None
    if status_id == STATUS_ID_ABANDONED and project.abandon_reason:
        extra = [{"field": "abandon_reason", "old": None, "new": project.abandon_reason}]
    record_status_change(
        session,
        entity_type="patent",
        entity_id=project.id,
        entity_label=project.docket_no,
        old_status=old_label,
        new_status=status_label(status_id),
        extra_changes=extra,
    )
    if status_id == STATUS_ID_FER_ISSUED and status_date:
        upsert_form3_updated_entry(session, project_id, status_date)
    if status_id == STATUS_ID_GRANTED and status_date:
        upsert_form27_entry(session, project_id, status_date, project.grant_number)
    session.commit()
    return _project_to_response(session, project)


VALID_CLIENT_TYPES = {"patent", "trademark", "design"}


def _validate_client_types(client_types: list[str]) -> None:
    if not client_types:
        raise ValueError("Select at least one client type")
    unknown = set(client_types) - VALID_CLIENT_TYPES
    if unknown:
        raise ValueError(f"Unknown client type(s): {', '.join(sorted(unknown))}")


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
                "client_types": json.loads(client.client_types or "[]"),
            }
        )
    return out


def create_patent_client(session: Session, payload: PatentClientInput) -> dict:
    _validate_client_types(payload.client_types)
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
        client_types=json.dumps(payload.client_types),
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
        "client_types": payload.client_types,
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


def update_patent_client(session: Session, client_id: int, payload: PatentClientUpdate) -> dict | None:
    client = session.get(PatentClient, client_id)
    if not client:
        return None

    _validate_client_types(payload.client_types)

    normalized_code = payload.client_code.upper()
    existing = session.exec(
        select(PatentClient).where(PatentClient.client_code == normalized_code)
    ).first()
    if existing and existing.id != client_id:
        raise ValueError("Client code already exists")

    client.client_code = normalized_code
    client.name = payload.name
    client.address = payload.address
    client.email = payload.email
    client.key_contacts = json.dumps(payload.key_contacts)
    client.docketing_email = payload.docketing_email
    client.client_types = json.dumps(payload.client_types)
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
        "client_types": payload.client_types,
    }


def delete_patent_client(session: Session, client_id: int) -> bool:
    client = session.get(PatentClient, client_id)
    if not client:
        return False
    try:
        session.delete(client)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("Cannot delete client because it is used in existing patent projects") from exc
    return True


def update_patent_agent(session: Session, agent_id: int, payload: PatentAgentUpdate) -> PatentAgent | None:
    agent = session.get(PatentAgent, agent_id)
    if not agent:
        return None

    existing = session.exec(select(PatentAgent).where(PatentAgent.agent_code == payload.agent_code)).first()
    if existing and existing.id != agent_id:
        raise ValueError("Patent agent code already exists")

    agent.name = payload.name
    agent.agent_code = payload.agent_code
    agent.address = payload.address
    agent.mobile_1 = payload.mobile_1
    agent.mobile_2 = payload.mobile_2
    agent.email_1 = payload.email_1
    agent.email_2 = payload.email_2
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent


def delete_patent_agent(session: Session, agent_id: int) -> bool:
    agent = session.get(PatentAgent, agent_id)
    if not agent:
        return False
    try:
        session.delete(agent)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ValueError("Cannot delete attorney because it is used in existing patent projects") from exc
    return True


def _annuity_grant_date(session: Session, project_id: int) -> date | None:
    event = session.exec(
        select(PatentStatusEvent).where(
            PatentStatusEvent.project_id == project_id,
            PatentStatusEvent.status_id == STATUS_ID_GRANTED,
        )
    ).first()
    return event.status_date if event else None


def get_annuity_summary(session: Session, project_id: int) -> PatentAnnuitySummary | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None

    filing_date = project.in_application_date
    grant_date = _annuity_grant_date(session, project_id)

    payments = session.exec(
        select(PatentAnnuityPayment)
        .where(PatentAnnuityPayment.project_id == project_id)
        .order_by(PatentAnnuityPayment.payment_date.asc(), PatentAnnuityPayment.id.asc())
    ).all()

    years_by_payment: dict[int, list[int]] = {}
    for payment in payments:
        rows = session.exec(
            select(PatentAnnuityPaymentYear)
            .where(PatentAnnuityPaymentYear.payment_id == payment.id)
            .order_by(PatentAnnuityPaymentYear.renewal_year.asc())
        ).all()
        years_by_payment[payment.id] = [row.renewal_year for row in rows]

    paid_years = sorted({year for years in years_by_payment.values() for year in years})

    payment_reads = [
        PatentAnnuityPaymentRead(
            id=payment.id,
            payment_date=payment.payment_date,
            total_fee=payment.total_fee,
            years=years_by_payment[payment.id],
            years_label=annuity.format_year_range(years_by_payment[payment.id]),
        )
        for payment in payments
    ]

    year_to_payment_id = {
        year: payment.id for payment in payments for year in years_by_payment[payment.id]
    }

    schedule: list[PatentAnnuityScheduleRow] = []
    if filing_date:
        for year in range(annuity.FIRST_RENEWAL_YEAR, annuity.LAST_RENEWAL_YEAR + 1):
            schedule.append(
                PatentAnnuityScheduleRow(
                    year=year,
                    due_date=annuity.renewal_year_date(filing_date, year),
                    fee=annuity.fee_for_year(year),
                    status="paid" if year in year_to_payment_id else "unpaid",
                    payment_id=year_to_payment_id.get(year),
                )
            )

    paid_till_yr = annuity.paid_till_year(paid_years)
    paid_till_dt = annuity.paid_till_date(filing_date, paid_years) if filing_date else None
    next_year = annuity.next_unpaid_year(paid_years)
    next_due_date = (
        annuity.renewal_year_date(filing_date, next_year)
        if filing_date and next_year <= annuity.LAST_RENEWAL_YEAR
        else None
    )

    accumulated_unpaid: list[int] = []
    is_post_grant_pending = False
    if filing_date and grant_date and not paid_years:
        accumulated = [
            year
            for year in annuity.accumulated_due_years_at_grant(filing_date, grant_date)
            if year not in paid_years
        ]
        if accumulated:
            accumulated_unpaid = accumulated
            is_post_grant_pending = True
            next_year = min(accumulated)
            next_due_date = annuity.post_grant_payment_deadline(grant_date)

    is_transferred = project.annuity_transferred_at is not None
    if is_transferred:
        # Case is locked: no further reminder of any kind, ever, regardless
        # of what's paid. Schedule/payment history stay visible (still a
        # useful historical record), only the "what's due next" signals
        # are suppressed.
        next_year = None
        next_due_date = None
        is_post_grant_pending = False
        accumulated_unpaid = []

    return PatentAnnuitySummary(
        filing_date=filing_date,
        grant_date=grant_date,
        fee_category=annuity.DEFAULT_FEE_CATEGORY,
        schedule=schedule,
        payments=payment_reads,
        paid_years=paid_years,
        paid_till_year=paid_till_yr,
        paid_till_date=paid_till_dt,
        next_due_year=(next_year if next_year and next_year <= annuity.LAST_RENEWAL_YEAR else None),
        next_due_date=next_due_date,
        is_post_grant_deadline_pending=is_post_grant_pending,
        accumulated_unpaid_years=accumulated_unpaid,
        orphaned_paid_years=annuity.orphaned_paid_years(paid_years),
        is_transferred=is_transferred,
        transferred_at=project.annuity_transferred_at,
        transferred_comment=project.annuity_transferred_comment,
    )


def record_annuity_payment(
    session: Session, project_id: int, payload: PatentAnnuityPaymentInput
) -> PatentAnnuitySummary | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    if project.annuity_transferred_at is not None:
        raise ValueError("This docket's annuity case has been marked transferred; no further payments can be recorded")
    if not project.in_application_date:
        raise ValueError("Filing (IN application) date is required before recording an annuity payment")

    years = sorted(set(payload.years))
    if len(years) != len(payload.years):
        raise ValueError("Duplicate renewal years in the same payment are not allowed")
    for year in years:
        annuity.validate_renewal_year(year)

    already_paid = set(_annuity_paid_years(session, project_id))
    duplicates = [year for year in years if year in already_paid]
    if duplicates:
        label = ", ".join(str(year) for year in duplicates)
        raise ValueError(f"Renewal year(s) {label} already paid")

    total_fee = annuity.compute_fee_for_years(years)
    payment = PatentAnnuityPayment(
        project_id=project_id,
        payment_date=payload.payment_date,
        total_fee=total_fee,
    )
    session.add(payment)
    session.flush()
    for year in years:
        session.add(PatentAnnuityPaymentYear(payment_id=payment.id, renewal_year=year))

    all_paid_years = sorted(already_paid | set(years))
    project.annuity_paid_upto = annuity.paid_till_date(project.in_application_date, all_paid_years)
    next_year = annuity.next_unpaid_year(all_paid_years)
    project.next_annuity_due = (
        annuity.renewal_year_date(project.in_application_date, next_year)
        if next_year <= annuity.LAST_RENEWAL_YEAR
        else None
    )
    project.modified_date = datetime.utcnow()
    session.add(project)
    session.commit()

    return get_annuity_summary(session, project_id)


def transfer_annuity_case(
    session: Session, project_id: int, payload: PatentAnnuityTransferInput
) -> PatentAnnuitySummary | None:
    project = session.get(PatentProject, project_id)
    if not project:
        return None
    if project.annuity_transferred_at is not None:
        raise ValueError("This docket's annuity case is already marked transferred")

    comment = payload.comment.strip()
    if not comment:
        raise ValueError("A comment is required to mark the annuity case as transferred")

    project.annuity_transferred_at = datetime.utcnow()
    project.annuity_transferred_comment = comment
    project.modified_date = datetime.utcnow()
    session.add(project)
    session.commit()

    return get_annuity_summary(session, project_id)
