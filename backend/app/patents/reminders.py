from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from .patent_status_catalog import (
    STATUS_ID_APPLICATION_FILED,
    STATUS_ID_FER_ISSUED,
    STATUS_ID_FER_RESPONSE_SUBMITTED,
    STATUS_ID_HEARING,
    STATUS_ID_REQUEST_FOR_EXAMINATION,
    TERMINAL_STATUS_IDS,
)
from .workflow import compute_rfe_deadline


@dataclass(frozen=True)
class NextPatentAction:
    message: str
    due_date: date


def _add_months(value: date, months: int) -> date:
    month = value.month + months
    year = value.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def compute_next_patent_action(
    *,
    filled: Mapping[int, date],
    current_status_id: int | None,
    in_application_date: date | None,
    priority_dates: Sequence[date] = (),
) -> NextPatentAction | None:
    if current_status_id is not None and current_status_id in TERMINAL_STATUS_IDS:
        return None

    if current_status_id == STATUS_ID_HEARING:
        hearing_date = filled.get(STATUS_ID_HEARING)
        if hearing_date:
            return NextPatentAction(message="Hearing", due_date=hearing_date)
        return None

    if current_status_id == STATUS_ID_FER_ISSUED:
        fer_date = filled.get(STATUS_ID_FER_ISSUED)
        if fer_date:
            return NextPatentAction(
                message="FER Response",
                due_date=_add_months(fer_date, 6),
            )
        return None

    if current_status_id == STATUS_ID_REQUEST_FOR_EXAMINATION:
        return None

    if current_status_id == STATUS_ID_FER_RESPONSE_SUBMITTED:
        return None

    if STATUS_ID_REQUEST_FOR_EXAMINATION not in filled:
        filing_date = in_application_date or filled.get(STATUS_ID_APPLICATION_FILED)
        if filing_date:
            return NextPatentAction(
                message="Request for Examination",
                due_date=compute_rfe_deadline(filing_date, priority_dates),
            )

    return None
