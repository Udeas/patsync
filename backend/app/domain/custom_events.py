"""Custom event reminder options, shared by the patent and trademark modules.

Both modules attach ad-hoc user-defined events (e.g. "Notice u/s 132",
"Form-13 (amendment)") to a project/application with an optional reminder.
The reminder is a follow-up due date AFTER the event (e.g. "respond within
15 days of this notice"), not an advance warning before it. The reminder
date is computed once at creation time and stored - custom events are
create + close only (no edit), so there is nothing to recompute later.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

REMINDER_OPTION_NONE = "none"
REMINDER_OPTION_15_DAYS = "15d"
REMINDER_OPTION_1_MONTH = "1m"
REMINDER_OPTION_3_MONTHS = "3m"

REMINDER_OPTION_LABELS = {
    REMINDER_OPTION_NONE: "No Reminder Required",
    REMINDER_OPTION_15_DAYS: "15 Days",
    REMINDER_OPTION_1_MONTH: "1 Month",
    REMINDER_OPTION_3_MONTHS: "3 Months",
}

VALID_REMINDER_OPTIONS = set(REMINDER_OPTION_LABELS)

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_short_date(d: date) -> str:
    """DD-Mon-YYYY, matching the app's date display convention (locale-independent)."""
    return f"{d.day:02d}-{_MONTH_ABBR[d.month - 1]}-{d.year}"


def _add_calendar_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(d.day, last_day)
    return date(year, month, day)


def compute_reminder_date(event_date: date, reminder_option: str) -> date | None:
    """Reminder fires N after event_date; None means no reminder requested."""
    if reminder_option == REMINDER_OPTION_NONE:
        return None
    if reminder_option == REMINDER_OPTION_15_DAYS:
        return event_date + timedelta(days=15)
    if reminder_option == REMINDER_OPTION_1_MONTH:
        return _add_calendar_months(event_date, 1)
    if reminder_option == REMINDER_OPTION_3_MONTHS:
        return _add_calendar_months(event_date, 3)
    raise ValueError(f"Unknown reminder_option: {reminder_option}")


def validate_reminder_option(value: str) -> str:
    if value not in VALID_REMINDER_OPTIONS:
        raise ValueError(
            "reminder_option must be one of: " + ", ".join(sorted(VALID_REMINDER_OPTIONS))
        )
    return value
