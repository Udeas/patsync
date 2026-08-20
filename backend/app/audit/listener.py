from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import event, inspect
from sqlmodel import Session

from app.audit.context import get_actor, get_request_ip, get_request_user_agent, is_explicit
from app.auth.models import AuditLog
from app.models.applications import ApplicationData
from app.models.trademark import TmApplicationData
from app.patents.models import PatentAgent, PatentClient, PatentProject

# model -> (entity_type, label attribute)
_AUDITED = {
    PatentProject: ("patent", "docket_no"),
    ApplicationData: ("design", "project_code"),
    TmApplicationData: ("trademark", "project_code"),
    PatentClient: ("client", "name"),
    PatentAgent: ("agent", "name"),
}
_IGNORE = {"created_date", "modified_date", "last_status_updated_at", "created_at", "updated_at"}
_UPDATE_SENTINELS = {"modified_date", "updated_at"}  # presence => an intentional update


def _coerce(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _label(obj, attr: str) -> str:
    return str(getattr(obj, attr, None) or "")[:255]


def _identity(obj) -> Optional[int]:
    ident = inspect(obj).identity
    return ident[0] if ident else None


def _fetch_committed_row(session, obj) -> dict:
    """Fetch the currently-committed DB row for obj (used to recover expired old values)."""
    table = obj.__class__.__table__
    pk_col = list(table.primary_key.columns)[0]
    pk_val = _identity(obj)
    if pk_val is None:
        return {}
    conn = session.connection()
    row = conn.execute(table.select().where(pk_col == pk_val)).mappings().first()
    return dict(row) if row else {}


def _scalar_diff(session, obj):
    """Return a list of {field, old, new} for scalar changes, fetching DB row when needed."""
    inst = inspect(obj)
    # Check if any changed attribute is missing its old value (expired-before-assign)
    needs_db_fetch = any(
        attr.history.has_changes() and attr.history.added and not attr.history.deleted
        for attr in inst.attrs
        if attr.key not in _IGNORE
    )
    db_vals: dict = _fetch_committed_row(session, obj) if needs_db_fetch else {}

    changes = []
    for attr in inst.attrs:
        if attr.key in _IGNORE:
            continue
        hist = attr.history
        if not hist.has_changes():
            continue
        new_val = hist.added[0] if hist.added else None
        old_val = hist.deleted[0] if hist.deleted else db_vals.get(attr.key)
        # Skip no-op writes (same value assigned, old value expired → looks like change)
        if new_val == old_val:
            continue
        changes.append({"field": attr.key, "old": _coerce(old_val), "new": _coerce(new_val)})
    return changes


def _update_touched(obj) -> bool:
    return any(inspect(obj).attrs[k].history.has_changes() for k in _UPDATE_SENTINELS if k in inspect(obj).attrs)


def _before_flush(session, flush_context, instances):
    pending = session.info.setdefault("_audit_pending", [])

    for obj in session.new:
        meta = _AUDITED.get(type(obj))
        if not meta:
            continue
        etype, label_attr = meta
        pending.append({"obj": obj, "action": "create", "entity_type": etype,
                        "label_attr": label_attr, "entity_id": None, "changes": [], "label": None})

    for obj in session.dirty:
        meta = _AUDITED.get(type(obj))
        if not meta:
            continue
        etype, label_attr = meta
        eid = _identity(obj)
        if is_explicit(session, etype, eid):
            continue
        changes = _scalar_diff(session, obj)
        if not changes and not _update_touched(obj):
            continue
        pending.append({"obj": obj, "action": "update", "entity_type": etype,
                        "label_attr": label_attr, "entity_id": eid, "changes": changes, "label": None})

    for obj in session.deleted:
        meta = _AUDITED.get(type(obj))
        if not meta:
            continue
        etype, label_attr = meta
        pending.append({"obj": None, "action": "delete", "entity_type": etype,
                        "label_attr": None, "entity_id": _identity(obj), "changes": [],
                        "label": _label(obj, label_attr)})


def _after_flush(session, flush_context):
    pending = session.info.get("_audit_pending")
    if not pending:
        return
    session.info["_audit_pending"] = []
    actor = get_actor()
    ip = get_request_ip()
    user_agent = get_request_user_agent()
    rows = []
    for p in pending:
        obj = p["obj"]
        if obj is not None:
            entity_id = getattr(obj, "id", None)
            label = _label(obj, p["label_attr"]) if p["label_attr"] else ""
        else:
            entity_id = p["entity_id"]
            label = p["label"] or ""
        rows.append({
            "created_at": datetime.utcnow(),
            "actor_user_id": actor.user_id if actor else None,
            "actor_username": actor.username if actor else None,
            "action": p["action"],
            "entity_type": p["entity_type"],
            "entity_id": entity_id,
            "entity_label": label,
            "changes": json.dumps(p["changes"]),
            "ip_address": ip,
            "user_agent": user_agent,
        })
    if rows:
        session.connection().execute(AuditLog.__table__.insert(), rows)


def register_audit_listener() -> None:
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)
