from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List

from app.tm_status_catalog import (
    STATUS_TM_FER_ISSUED,
    STATUS_TM_HEARING,
    STATUS_TM_REGISTERED,
)


def add_one_calendar_month(d: date) -> date:
    month = d.month + 1
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


@dataclass(frozen=True)
class ReminderComputation:
    kind: str
    fire_on: date
    label: str


@dataclass(frozen=True)
class TmTimelineComputation:
    filing_date: date | None
    fer_followup_due: date | None
    hearing_due: date | None
    upcoming_reminders: List[ReminderComputation]


def _date_for_status(
    states_ordered: list[tuple[int, date, str]],
    status_name: str,
) -> date | None:
    for _, ad, name in states_ordered:
        if name == status_name:
            return ad
    return None


def build_timeline_for_tm_application(
    *,
    states_ordered: list[tuple[int, date, str]],
    current_status_name: str,
    today: date,
) -> TmTimelineComputation:
    """
    Trademark reminders (only two):
    - FER Issued date + 1 month (reminder on that follow-up date).
    - Hearing Issued date: reminder 3 days before the hearing due date.
    """
    filing = _date_for_status(states_ordered, "Application filed")
    fer_issued = _date_for_status(states_ordered, STATUS_TM_FER_ISSUED)
    hearing = _date_for_status(states_ordered, STATUS_TM_HEARING)

    fer_followup = add_one_calendar_month(fer_issued) if fer_issued else None
    upcoming: List[ReminderComputation] = []

    if current_status_name != STATUS_TM_REGISTERED and fer_issued and fer_followup:
        if current_status_name == STATUS_TM_FER_ISSUED and fer_followup >= today:
            upcoming.append(
                ReminderComputation(
                    kind="fer_followup",
                    fire_on=fer_followup,
                    label="FER follow-up due (1 month after FER Issued)",
                )
            )

    if current_status_name == STATUS_TM_HEARING and hearing:
        hearing_reminder = hearing - timedelta(days=3)
        if hearing_reminder >= today:
            upcoming.append(
                ReminderComputation(
                    kind="hearing",
                    fire_on=hearing_reminder,
                    label="Hearing in 3 days",
                )
            )

    merged = sorted(upcoming, key=lambda r: (r.fire_on, r.kind))
    return TmTimelineComputation(
        filing_date=filing,
        fer_followup_due=fer_followup,
        hearing_due=hearing,
        upcoming_reminders=merged,
    )
