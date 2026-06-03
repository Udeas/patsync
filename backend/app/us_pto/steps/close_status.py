from __future__ import annotations

from datetime import datetime

from googleapiclient.errors import HttpError

from app.us_pto.auth.calendar import get_calendar_service
from app.us_pto.config import CALENDAR_ID, CLOSURE_NOTE
from app.us_pto.repository import (
    init_db,
    list_done_entries_for_closure,
    mark_closure_processed,
    update_entry,
)


def normalize_cell_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_event_ids(cell_value) -> list[str]:
    raw = normalize_cell_value(cell_value)
    if not raw:
        return []
    return [item.strip() for item in raw.replace("|", " | ").split(" | ") if item.strip()]


def append_closure_note(status_value: str) -> str:
    current = normalize_cell_value(status_value)
    if CLOSURE_NOTE in current:
        return current
    if not current:
        return CLOSURE_NOTE
    return f"{current} | {CLOSURE_NOTE}"


def is_future_event(event: dict) -> bool:
    start_info = event.get("start", {})
    date_value = start_info.get("date") or start_info.get("dateTime", "")[:10]
    if not date_value:
        return False
    event_date = datetime.strptime(date_value, "%Y-%m-%d").date()
    return event_date >= datetime.today().date()


def close_future_events_for_entries(service, entries: list[dict], *, mark_processed: bool = False) -> dict:
    closed_count = 0
    updated_entries = 0
    errors: list[str] = []

    for entry in entries:
        entry_id = entry["id"]
        event_ids = parse_event_ids(entry.get("calendar_event_ids", ""))
        if not event_ids:
            continue

        updated_any = False
        for event_id in event_ids:
            try:
                event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
            except HttpError as exc:
                errors.append(f"Entry {entry_id} event {event_id}: {exc}")
                continue

            if not is_future_event(event):
                continue

            summary = event.get("summary", "")
            if summary.startswith("[Closed]"):
                continue

            event["summary"] = f"[Closed] {summary}"
            try:
                service.events().update(calendarId=CALENDAR_ID, eventId=event_id, body=event).execute()
                updated_any = True
                closed_count += 1
            except HttpError as exc:
                errors.append(f"Entry {entry_id} update {event_id}: {exc}")

        if updated_any:
            update_entry(
                entry_id,
                calendar_status=append_closure_note(entry.get("calendar_status", "")),
            )
            updated_entries += 1
            if mark_processed:
                mark_closure_processed(entry_id)

    return {
        "closed_event_count": closed_count,
        "updated_entry_count": updated_entries,
        "errors": errors,
    }


def run_close_status_for_ui(entry_ids: list[int] | None = None) -> dict:
    init_db()
    entries = list_done_entries_for_closure(entry_ids=entry_ids)
    if not entries:
        return {
            "status": "info",
            "message": "No Done rows with calendar events to close.",
            "closed_event_count": 0,
            "updated_entry_count": 0,
        }

    service = get_calendar_service()
    result = close_future_events_for_entries(service, entries, mark_processed=True)
    status = "success" if not result["errors"] else "partial"
    return {
        "status": status,
        "message": f"Closed {result['closed_event_count']} future event(s) across {result['updated_entry_count']} row(s).",
        **result,
    }
