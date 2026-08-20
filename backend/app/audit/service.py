from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from app.audit.context import get_actor, get_request_ip, get_request_user_agent, mark_explicit
from app.auth.models import AuditLog


def _safe(value):
    from datetime import date, datetime
    from decimal import Decimal
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _coerce_changes(changes):
    out = []
    for c in changes or []:
        out.append({k: _safe(v) for k, v in c.items()})
    return out


def write_audit(session, *, action: str, entity_type: Optional[str] = None,
                entity_id: Optional[int] = None, entity_label: Optional[str] = None,
                changes: Optional[list] = None, ip_address: Optional[str] = None,
                user_agent: Optional[str] = None, actor=None) -> None:
    actor = actor if actor is not None else get_actor()
    ip_address = ip_address if ip_address is not None else get_request_ip()
    user_agent = user_agent if user_agent is not None else get_request_user_agent()
    session.add(AuditLog(
        created_at=datetime.utcnow(),
        actor_user_id=actor.user_id if actor else None,
        actor_username=actor.username if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=(entity_label[:255] if entity_label else entity_label),
        changes=json.dumps(_coerce_changes(changes)),
        ip_address=ip_address,
        user_agent=user_agent,
    ))


def record_status_change(session, *, entity_type: str, entity_id: int, entity_label: str,
                         old_status: Optional[str], new_status: str,
                         extra_changes: Optional[list] = None) -> None:
    mark_explicit(session, entity_type, entity_id)
    changes = [{"field": "status", "old": old_status, "new": new_status}]
    if extra_changes:
        changes.extend(extra_changes)
    write_audit(session, action="status_change", entity_type=entity_type,
                entity_id=entity_id, entity_label=entity_label, changes=changes)
