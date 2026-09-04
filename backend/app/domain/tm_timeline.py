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


def add_years(d: date, years: int) -> date:
    """Add N calendar years, clamping Feb 29 -> Feb 28 on a non-leap target
    year (mirrors add_one_calendar_month's day-clamping approach)."""
    year = d.year + years
    last_day = calendar.monthrange(year, d.month)[1]
    day = min(d.day, last_day)
    return date(year, d.month, day)


@dataclass(frozen=True)
class ReminderComputation:
    kind: str
    fire_on: date
    label: str


RENEWAL_YEARS_FROM_FILING = 10


@dataclass(frozen=True)
class TmTimelineComputation:
    filing_date: date | None
    fer_followup_due: date | None
    hearing_due: date | None
    renewal_due: date | None
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
    Trademark reminders:
    - FER Issued date + 1 month (reminder on that follow-up date).
    - Hearing Issued date: reminder 3 days before the hearing due date.
    - Registered: renewal due 10 years after the application (filing) date -
      the next step once the mark is registered. Not gated on today, unlike
      the two reminders above, so an overdue renewal keeps showing instead
      of silently disappearing.
    """
    filing = _date_for_status(states_ordered, "Application filed")
    fer_issued = _date_for_status(states_ordered, STATUS_TM_FER_ISSUED)
    hearing = _date_for_status(states_ordered, STATUS_TM_HEARING)

    fer_followup = add_one_calendar_month(fer_issued) if fer_issued else None
    renewal_due = add_years(filing, RENEWAL_YEARS_FROM_FILING) if filing else None
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

    if current_status_name == STATUS_TM_REGISTERED and renewal_due:
        upcoming.append(
            ReminderComputation(
                kind="renewal",
                fire_on=renewal_due,
                label="Trademark Renewal Due",
            )
        )

    merged = sorted(upcoming, key=lambda r: (r.fire_on, r.kind))
    return TmTimelineComputation(
        filing_date=filing,
        fer_followup_due=fer_followup,
        hearing_due=hearing,
        renewal_due=renewal_due,
        upcoming_reminders=merged,
    )
