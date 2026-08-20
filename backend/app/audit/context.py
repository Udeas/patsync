from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AuditActor:
    user_id: Optional[int]
    username: Optional[str]


_current_actor: contextvars.ContextVar[Optional[AuditActor]] = contextvars.ContextVar(
    "audit_actor", default=None
)


def set_actor(user_id: Optional[int], username: Optional[str]) -> None:
    _current_actor.set(AuditActor(user_id=user_id, username=username))


def get_actor() -> Optional[AuditActor]:
    return _current_actor.get()


_MARKER_KEY = "_audit_explicit"


def mark_explicit(session, entity_type: str, entity_id: Optional[int]) -> None:
    marker = session.info.setdefault(_MARKER_KEY, set())
    marker.add((entity_type, entity_id))


def is_explicit(session, entity_type: str, entity_id: Optional[int]) -> bool:
    marker = session.info.get(_MARKER_KEY)
    return bool(marker) and (entity_type, entity_id) in marker
