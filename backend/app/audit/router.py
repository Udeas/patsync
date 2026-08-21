from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.audit.schemas import AuditListResponse, AuditLogRead
from app.auth.models import AuditLog
from app.database import get_session

router = APIRouter()


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
    actor: Optional[str] = None,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    session: Session = Depends(get_session),
):
    filters = []
    if actor:
        filters.append(func.lower(AuditLog.actor_username).like(f"%{actor.lower()}%"))
    if entity_type:
        filters.append(AuditLog.entity_type == entity_type)
    if action:
        filters.append(AuditLog.action == action)
    if date_from:
        filters.append(AuditLog.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        filters.append(AuditLog.created_at <= datetime.combine(date_to, time.max))

    count_stmt = select(func.count()).select_from(AuditLog)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = session.exec(count_stmt).one()

    stmt = select(AuditLog)
    for f in filters:
        stmt = stmt.where(f)
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = session.exec(stmt).all()

    return AuditListResponse(
        items=[_to_read(r) for r in rows],
        total=int(total),
        page=page,
        page_size=page_size,
    )
