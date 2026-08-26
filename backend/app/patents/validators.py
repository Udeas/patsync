from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .schemas import PatentProjectCreate

IN_APPLICATION_PATTERN = re.compile(r"^\d{12}$")
PCT_APPLICATION_PATTERN = re.compile(r"^PCT/[A-Z]{2}\d{4}/\d{6}$")

JURISDICTION_LABELS = {
    "1": "Delhi",
    "2": "Mumbai",
    "3": "Kolkata",
    "4": "Chennai",
}

TYPE_LABELS = {
    "1": "Ordinary",
    "2": "Ordinary Divisional",
    "3": "Ordinary-Patent of Addition",
    "4": "Convention",
    "5": "Convention divisional",
    "6": "Convention - Patent of Addition",
    "7": "PCT National Phase Entry",
    "8": "PCT National Phase Entry - Divisional",
    "9": "PCT National Phase Entry - Patent of Addition",
}

CONVENTION_APPLICATION_TYPES = frozenset(
    {
        "Convention",
        "Convention divisional",
        "Convention - Patent of Addition",
    }
)

PCT_APPLICATION_TYPES = frozenset(
    {
        "PCT National Phase Entry",
        "PCT National Phase Entry - Divisional",
        "PCT National Phase Entry - Patent of Addition",
    }
)

# Divisional-family applications are a child application distinct from the
# parent they were carved out of. Their own IN application no/date do not
# need to satisfy the usual year-match / priority-window date checks
# against the parent's data, since those checks were already satisfied by
# the parent application itself.
DIVISIONAL_APPLICATION_TYPES = frozenset(
    {
        "Ordinary Divisional",
        "Convention divisional",
        "PCT National Phase Entry - Divisional",
    }
)


@dataclass(frozen=True)
class ApplicationDetermination:
    raw_number: str
    filing_year: int
    jurisdiction_code: str
    jurisdiction_name: str
    type_code: str
    type_name: str
    serial_number: str
    bucket: str


def _add_calendar_months(value: date, months: int) -> date:
    month = value.month + months
    year = value.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def parse_in_application_number(value: str) -> ApplicationDetermination:
    if not IN_APPLICATION_PATTERN.fullmatch(value):
        raise ValueError("IN application number must be 12 numeric digits")

    filing_year = int(value[:4])
    jurisdiction_code = value[4]
    type_code = value[5]
    serial_number = value[6:]
    jurisdiction_name = JURISDICTION_LABELS.get(jurisdiction_code)
    type_name = TYPE_LABELS.get(type_code)

    if jurisdiction_name is None:
        raise ValueError("Unknown jurisdiction code in IN application number")
    if type_name is None:
        raise ValueError("Unknown type code in IN application number")

    if type_code in {"1", "2", "3"}:
        bucket = "1_2_3"
    elif type_code in {"4", "5", "6"}:
        bucket = "4_5_6"
    else:
        bucket = "7_8_9"

    return ApplicationDetermination(
        raw_number=value,
        filing_year=filing_year,
        jurisdiction_code=jurisdiction_code,
        jurisdiction_name=jurisdiction_name,
        type_code=type_code,
        type_name=type_name,
        serial_number=serial_number,
        bucket=bucket,
    )


def validate_pct_international_number(value: str) -> str:
    if not PCT_APPLICATION_PATTERN.fullmatch(value):
        raise ValueError("International application number must match PCT/CCYYYY/XXXXXX")
    return value


def validate_in_within_months_of_anchor(
    *,
    in_application_date: date,
    anchor_date: date,
    months: int,
    anchor_label: str,
) -> None:
    if in_application_date < anchor_date:
        raise ValueError(f"IN application date cannot be earlier than {anchor_label}")
    deadline = _add_calendar_months(anchor_date, months)
    if in_application_date > deadline:
        raise ValueError(
            f"IN application date must be within {months} months of {anchor_label}"
        )


def validate_priority_date_within_window(priority_date: date, in_application_date: date) -> None:
    validate_in_within_months_of_anchor(
        in_application_date=in_application_date,
        anchor_date=priority_date,
        months=12,
        anchor_label="priority application date",
    )


def validate_pct_date_within_window(international_date: date, in_application_date: date) -> None:
    validate_in_within_months_of_anchor(
        in_application_date=in_application_date,
        anchor_date=international_date,
        months=31,
        anchor_label="international application date",
    )


def validate_in_application_date_for_draft(in_application_date: date, current_date: date) -> None:
    if in_application_date != current_date:
        raise ValueError("For draft projects, IN filing date must match the current date")


def validate_divisional_parent_application(payload: "PatentProjectCreate") -> None:
    if payload.project_mode != "final":
        return
    application_type = (payload.application_type or "").strip()
    if application_type not in DIVISIONAL_APPLICATION_TYPES:
        return
    if not payload.parent_application_no or not payload.parent_application_date:
        raise ValueError(
            "Parent application number and date are required for divisional Final Docket"
        )


def validate_create_project_filing_windows(payload: "PatentProjectCreate") -> None:
    application_type = (payload.application_type or "").strip()
    if application_type in DIVISIONAL_APPLICATION_TYPES:
        return

    if payload.project_mode == "draft" or not payload.in_application_date:
        return

    in_date = payload.in_application_date

    if application_type in CONVENTION_APPLICATION_TYPES:
        if not payload.priorities:
            raise ValueError("At least one conventional priority application is required")
        for priority in payload.priorities:
            validate_in_within_months_of_anchor(
                in_application_date=in_date,
                anchor_date=priority.priority_application_date,
                months=12,
                anchor_label="priority application date",
            )
        return

    if application_type in PCT_APPLICATION_TYPES:
        wipo_only = bool(payload.pct_wipo_filed_only)
        if wipo_only and payload.priorities:
            raise ValueError(
                "Convention priority data is not allowed when Only WIPO filed application is selected"
            )
        if not wipo_only and not payload.priorities:
            raise ValueError("At least one conventional priority application is required")
        if not payload.international_applications:
            raise ValueError("At least one PCT international application is required")
        for international in payload.international_applications:
            validate_in_within_months_of_anchor(
                in_application_date=in_date,
                anchor_date=international.international_application_date,
                months=31,
                anchor_label="international application date",
            )
