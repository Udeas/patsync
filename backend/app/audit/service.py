from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from app.audit.context import get_actor, mark_explicit
from app.auth.models import AuditLog


def write_audit(session, *, action: str, entity_type: Optional[str] = None,
                entity_id: Optional[int] = None, entity_label: Optional[str] = None,
                changes: Optional[list] = None, ip_address: Optional[str] = None,
                actor=None) -> None:
    actor = actor if actor is not None else get_actor()
    session.add(AuditLog(
        created_at=datetime.utcnow(),
        actor_user_id=actor.user_id if actor else None,
        actor_username=actor.username if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        changes=json.dumps(changes or []),
        ip_address=ip_address,
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
