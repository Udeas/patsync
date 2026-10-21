from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.audit.schemas import AuditListResponse, AuditLogRead
from app.auth.models import AuditLog
from app.database import get_session
from app.patents.models import PatentProject

router = APIRouter()


def _matching_patent_ids_by_application_no(session: Session, term: str) -> list[int]:
    """Patent application numbers live on patent_project, not audit_log (it's
    already recorded there - no need to duplicate it onto every audit row).
    Resolved only when a free-text search is active, to join it into the
    audit query without an always-on JOIN."""
    stmt = select(PatentProject.id).where(func.lower(PatentProject.in_application_no).like(f"%{term}%"))
    return list(session.exec(stmt).all())


def _to_read(row: AuditLog) -> AuditLogRead:
    try:
        parsed = json.loads(row.changes) if row.changes else []
    except (ValueError, TypeError):
        parsed = []
    return AuditLogRead(
        id=row.id or 0,
        created_at=row.created_at,
        actor_username=row.actor_username,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        entity_label=row.entity_label,
        changes=parsed,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
    )


@router.get("", response_model=AuditListResponse)
def list_audit(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    q: Optional[str] = None,
    actor: Optional[str] = None,
    entity_type: Optional[str] = None,
    project: Optional[str] = None,
    field: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    session: Session = Depends(get_session),
):
    filters = []
    if actor:
        filters.append(func.lower(AuditLog.actor_username).like(f"%{actor.lower()}%"))
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    if project:
        filters.append(func.lower(AuditLog.entity_label).like(f"%{project.lower()}%"))
    if field:
        # changes is a serialized JSON array of {field, old, new} - a text
        # match on the json.dumps-rendered key is enough without needing a
        # JSON-aware column type (kept portable across SQLite/Postgres).
        filters.append(AuditLog.changes.like(f'%"field": "{field}"%'))
    if action:
        filters.append(AuditLog.action == action)
    if date_from:
        filters.append(AuditLog.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        filters.append(AuditLog.created_at <= datetime.combine(date_to, time.max))
    if q:
        term = q.strip().lower()
        q_filters = [
            func.lower(AuditLog.actor_username).like(f"%{term}%"),
            func.lower(AuditLog.entity_label).like(f"%{term}%"),
            func.lower(AuditLog.changes).like(f"%{term}%"),
        ]
        patent_ids = _matching_patent_ids_by_application_no(session, term)
        if patent_ids:
            q_filters.append((AuditLog.entity_type == "patent") & AuditLog.entity_id.in_(patent_ids))
        filters.append(or_(*q_filters))

    count_stmt = select(func.count()).select_from(AuditLog)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = session.exec(count_stmt).one()

    order = AuditLog.created_at.asc() if sort_dir == "asc" else AuditLog.created_at.desc()
    id_order = AuditLog.id.asc() if sort_dir == "asc" else AuditLog.id.desc()

    stmt = select(AuditLog)
    for f in filters:
        stmt = stmt.where(f)
    stmt = stmt.order_by(order, id_order)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = session.exec(stmt).all()

    return AuditListResponse(
        items=[_to_read(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )
