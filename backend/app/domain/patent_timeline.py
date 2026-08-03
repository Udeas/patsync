from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List

from app.status_catalog import (
    STATUS_ABANDONED,
    STATUS_APPLICATION_FILED,
    STATUS_CASE_UNDER_HEARING,
    STATUS_FER_ISSUED,
    STATUS_GRANTED,
)


def add_six_calendar_months(d: date) -> date:
    month = d.month + 6
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
class PatentTimelineComputation:
    filing_date: date | None
    fer_response_deadline: date | None
    upcoming_reminders: List[ReminderComputation]


def _first_filing_date(
    states_ordered: list[tuple[int, date, str]],
) -> date | None:
    for _, ad, name in states_ordered:
        if name == STATUS_APPLICATION_FILED:
            return ad
    return None


def _fer_reminders_for_deadline(
    deadline: date,
    today: date,
) -> List[ReminderComputation]:
    offsets = [
        (30, "FER response due in 30 days"),
        (15, "FER response due in 15 days"),
        (3, "FER response due in 3 days"),
    ]
    out: List[ReminderComputation] = []
    for days_before, label in offsets:
        fire_on = deadline - timedelta(days=days_before)
        if fire_on >= today:
            out.append(
                ReminderComputation(
                    kind="fer_deadline",
                    fire_on=fire_on,
                    label=label,
                )
            )
    return sorted(out, key=lambda r: r.fire_on)


def _hearing_reminders(
    hearing_date: date,
    today: date,
) -> List[ReminderComputation]:
    reminders: List[ReminderComputation] = []
    offsets = [(15, "Hearing in 15 days"), (3, "Hearing in 3 days")]
    for days_before, label in offsets:
        fire_on = hearing_date - timedelta(days=days_before)
        if fire_on >= today:
            reminders.append(
                ReminderComputation(kind="hearing", fire_on=fire_on, label=label)
            )
    if hearing_date >= today:
        reminders.append(
            ReminderComputation(kind="hearing", fire_on=hearing_date, label="Hearing date")
        )
    return sorted(reminders, key=lambda r: r.fire_on)


def build_timeline_for_application(
    *,
    states_ordered: list[tuple[int, date, str]],
    current_status_name: str,
    today: date,
) -> PatentTimelineComputation:
    """
    states_ordered: (application_state.id, application_date, status label) ascending by state id.

    Rules:
    - FER deadline is filing date + 6 calendar months.
    - FER window reminders only while current status is FER Issued (not under secrecy /
      not after moving to later stages via current status).
    - After FER Response submitted, FER deadline reminders are suppressed (handled by
      current status not being FER Issued).
    - Hearing reminders only while current status is Case under hearing; uses latest
      state's application_date as hearing date.
    - No reminders for Granted or Abandoned.
    """
    filing = _first_filing_date(states_ordered)
    fer_deadline = add_six_calendar_months(filing) if filing else None

    upcoming: List[ReminderComputation] = []

    if current_status_name not in (STATUS_GRANTED, STATUS_ABANDONED) and fer_deadline:
        if current_status_name == STATUS_FER_ISSUED:
            upcoming.extend(_fer_reminders_for_deadline(fer_deadline, today))

    if (
        current_status_name == STATUS_CASE_UNDER_HEARING
        and states_ordered
        and current_status_name not in (STATUS_GRANTED, STATUS_ABANDONED)
    ):
        _sid, hearing_date, _name = states_ordered[-1]
        upcoming.extend(_hearing_reminders(hearing_date, today))

    merged = sorted(upcoming, key=lambda r: (r.fire_on, r.kind))
    return PatentTimelineComputation(
        filing_date=filing,
        fer_response_deadline=fer_deadline,
        upcoming_reminders=merged,
    )
