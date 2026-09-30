from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List

from app.tm_status_catalog import (
    STATUS_TM_ACCEPTED_ADVERTISED,
    STATUS_TM_FER_ISSUED,
    STATUS_TM_FORMALITY_FAIL,
    STATUS_TM_HEARING,
    STATUS_TM_NOTICE_132_ISSUED,
    STATUS_TM_REGISTERED,
)


def add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


def add_one_calendar_month(d: date) -> date:
    return add_months(d, 1)


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
    formality_fail_followup_due: date | None
    fer_followup_due: date | None
    notice_132_followup_due: date | None
    hearing_due: date | None
    hearing_response_due: date | None
    registration_certificate_due: date | None
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
    registered_note: str | None = None,
) -> TmTimelineComputation:
    """
    Trademark reminders:
    - Formality Check Fail date + 1 month (reminder to respond).
    - FER Issued date + 1 month (reminder on that follow-up date).
    - Notice U/s 132 Issued date + 1 month (reminder on that follow-up date).
    - Hearing Issued date: reminder 3 days before the hearing, plus a second
      reminder 15 days after the hearing to file the written submissions.
    - Accepted & Advertised date + 3 months (reminder to expect/follow up on
      the registration certificate).
    - Registered: renewal due 10 years after the application (filing) date -
      the next step once the mark is registered.
    None of these are gated on today - an overdue reminder keeps showing
    (as overdue) instead of silently disappearing once its date passes.
    Most are gated on current_status_name (the combined dated/sub-status
    "current status" - see app.domain.tm_sub_status), so a reminder
    correctly drops once the project moves past the status it belongs to,
    whether that's a later dated milestone or an informative sub-status.
    "Registration Certificate Due" is the one exception: it requires BOTH
    the Registered date AND its Journal/Registration No. note to be filled
    (per product spec) before it clears - entering the Registered date
    alone (leaving the note blank) is not enough, so it's checked directly
    against registered_note rather than via current_status_name.
    """
    filing = _date_for_status(states_ordered, "Application filed")
    formality_fail = _date_for_status(states_ordered, STATUS_TM_FORMALITY_FAIL)
    fer_issued = _date_for_status(states_ordered, STATUS_TM_FER_ISSUED)
    notice_132 = _date_for_status(states_ordered, STATUS_TM_NOTICE_132_ISSUED)
    hearing = _date_for_status(states_ordered, STATUS_TM_HEARING)
    accepted_advertised = _date_for_status(states_ordered, STATUS_TM_ACCEPTED_ADVERTISED)
    registered_date = _date_for_status(states_ordered, STATUS_TM_REGISTERED)

    formality_fail_followup = add_one_calendar_month(formality_fail) if formality_fail else None
    fer_followup = add_one_calendar_month(fer_issued) if fer_issued else None
    notice_132_followup = add_one_calendar_month(notice_132) if notice_132 else None
    hearing_response_due = hearing + timedelta(days=15) if hearing else None
    registration_certificate_due = add_months(accepted_advertised, 3) if accepted_advertised else None
    registration_certificate_satisfied = registered_date is not None and bool(
        (registered_note or "").strip()
    )
    renewal_due = add_years(filing, RENEWAL_YEARS_FROM_FILING) if filing else None
    upcoming: List[ReminderComputation] = []

    if current_status_name == STATUS_TM_FORMALITY_FAIL and formality_fail_followup:
        upcoming.append(
            ReminderComputation(
                kind="formality_fail_followup",
                fire_on=formality_fail_followup,
                label="Formality Check Response Due",
            )
        )

    if current_status_name == STATUS_TM_FER_ISSUED and fer_followup:
        upcoming.append(
            ReminderComputation(
                kind="fer_followup",
                fire_on=fer_followup,
                label="FER Response Due",
            )
        )

    if current_status_name == STATUS_TM_NOTICE_132_ISSUED and notice_132_followup:
        upcoming.append(
            ReminderComputation(
                kind="notice_132_followup",
                fire_on=notice_132_followup,
                label="Notice U/s 132 Response Due",
            )
        )

    if current_status_name == STATUS_TM_HEARING and hearing:
        upcoming.append(
            ReminderComputation(
                kind="hearing",
                fire_on=hearing - timedelta(days=3),
                label="Hearing in 3 days",
            )
        )
        upcoming.append(
            ReminderComputation(
                kind="hearing_response",
                fire_on=hearing_response_due,
                label="Hearing Response Due",
            )
        )

    if (
        accepted_advertised
        and registration_certificate_due
        and not registration_certificate_satisfied
    ):
        upcoming.append(
            ReminderComputation(
                kind="registration_certificate_due",
                fire_on=registration_certificate_due,
                label="Registration Certificate Due",
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
        formality_fail_followup_due=formality_fail_followup,
        fer_followup_due=fer_followup,
        notice_132_followup_due=notice_132_followup,
        hearing_due=hearing,
        hearing_response_due=hearing_response_due,
        registration_certificate_due=registration_certificate_due,
        renewal_due=renewal_due,
        upcoming_reminders=merged,
    )
