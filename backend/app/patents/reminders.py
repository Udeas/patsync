from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from . import annuity
from .patent_status_catalog import (
    STATUS_ID_APPLICATION_FILED,
    STATUS_ID_FER_ISSUED,
    STATUS_ID_FER_RESPONSE_SUBMITTED,
    STATUS_ID_GRANTED,
    STATUS_ID_HEARING,
    STATUS_ID_NON_PROVISIONAL_APPLICATION,
    STATUS_ID_REQUEST_FOR_EXAMINATION,
    TERMINAL_STATUS_IDS,
)
from .validators import DIVISIONAL_APPLICATION_TYPES, PATENT_OF_ADDITION_APPLICATION_TYPES
from .workflow import (
    compute_divisional_rfe_deadline,
    compute_patent_of_addition_rfe_deadline,
    compute_rfe_deadline,
)


@dataclass(frozen=True)
class NextPatentAction:
    message: str
    due_date: date


def add_months(value: date, months: int) -> date:
    month = value.month + months
    year = value.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# Back-compat alias: the docket-entries feature (app/patents/docket.py) also
# imports this as the canonical calendar-month-add utility for statutory
# deadline math, matching the FER-response / provisional-to-complete dates
# computed below.
_add_months = add_months


def compute_next_patent_action(
    *,
    filled: Mapping[int, date],
    current_status_id: int | None,
    in_application_date: date | None,
    priority_dates: Sequence[date] = (),
    provisional_kind: str | None = None,
    application_type: str | None = None,
    parent_application_date: date | None = None,
    parent_priority_dates: Sequence[date] = (),
    grant_date: date | None = None,
    annuity_paid_years: Sequence[int] = (),
    is_annuity_transferred: bool = False,
) -> NextPatentAction | None:
    if current_status_id == STATUS_ID_GRANTED:
        # Granted is otherwise terminal (no further action) - but once
        # granted, renewal ("annuity") fees become the next thing due.
        # Once the case is marked transferred, it's locked: no further
        # annuity reminder is ever shown again, regardless of what's paid.
        if is_annuity_transferred:
            return None
        filing_date = in_application_date or filled.get(STATUS_ID_APPLICATION_FILED)
        action = annuity.compute_next_annuity_action(
            filing_date, grant_date or filled.get(STATUS_ID_GRANTED), annuity_paid_years
        )
        if action:
            return NextPatentAction(message=action.message, due_date=action.due_date)
        return None

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

    if provisional_kind == "OP" and STATUS_ID_NON_PROVISIONAL_APPLICATION not in filled:
        filing_date = in_application_date or filled.get(STATUS_ID_APPLICATION_FILED)
        if filing_date:
            return NextPatentAction(
                message="Non-Provisional Application",
                due_date=_add_months(filing_date, 12),
            )

    if STATUS_ID_REQUEST_FOR_EXAMINATION not in filled:
        # RFE runs off the application's own filing date - for a Provisional
        # (OP) docket that is the provisional's own filing date, which acts
        # as its priority date. The Non-Provisional/complete-specification
        # date is a separate 12-month deadline (handled above); it must NOT
        # replace the RFE anchor.
        filing_date = in_application_date or filled.get(STATUS_ID_APPLICATION_FILED)
        if filing_date:
            normalized_type = (application_type or "").strip()
            is_divisional = normalized_type in DIVISIONAL_APPLICATION_TYPES
            is_patent_of_addition = normalized_type in PATENT_OF_ADDITION_APPLICATION_TYPES
            if is_divisional and parent_application_date:
                deadline = compute_divisional_rfe_deadline(
                    filing_date, parent_application_date, parent_priority_dates
                )
            elif is_patent_of_addition:
                deadline = compute_patent_of_addition_rfe_deadline(
                    filing_date, priority_dates, parent_application_date, parent_priority_dates
                )
            else:
                deadline = compute_rfe_deadline(filing_date, priority_dates)
            return NextPatentAction(
                message="Request for Examination",
                due_date=deadline,
            )

    return None

