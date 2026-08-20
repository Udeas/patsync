from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: int
    created_at: datetime
    actor_username: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    entity_label: Optional[str] = None
    changes: List[Any] = []
    ip_address: Optional[str] = None


class AuditListResponse(BaseModel):
    items: List[AuditLogRead]
    total: int
    page: int
    page_size: int
