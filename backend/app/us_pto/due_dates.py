from __future__ import annotations

from datetime import datetime

from dateutil.relativedelta import relativedelta

from app.us_pto.doc_codes import get_rules_for_doc_code


def parse_event_date(value: str) -> datetime:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported event date format: {value!r}")


def compute_due_dates(doc_code: str, event_date_str: str) -> tuple[str | None, list[dict]]:
    rules = get_rules_for_doc_code(doc_code)
    if not rules:
        return None, []

    event_date = parse_event_date(event_date_str)
    due_date_rows: list[dict] = []
    final_due_date: str | None = None
    max_final_offset = 0

    for month_offset, label, final_due_month_offset in rules:
        due_date = event_date + relativedelta(months=month_offset)
        due_date_rows.append(
            {
                "label": label,
                "due_date": due_date.strftime("%Y-%m-%d"),
                "month_offset": month_offset,
            }
        )
        if final_due_month_offset >= max_final_offset:
            max_final_offset = final_due_month_offset
            final_due = event_date + relativedelta(months=final_due_month_offset)
            final_due_date = final_due.strftime("%Y-%m-%d")

    return final_due_date, due_date_rows
