from __future__ import annotations

import os
import re
from datetime import datetime
from html import escape

from dateutil.relativedelta import relativedelta

from app.us_pto.auth.calendar import get_calendar_service
from app.us_pto.config import CALENDAR_ID, HTML_BACKUP_FILE
from app.us_pto.repository import init_db, list_calendar_candidates, update_entry


def normalize_cell_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doc_code(value) -> str:
    return normalize_cell_value(value).upper()


def get_master_file_lock_status() -> dict:
    return {"is_ready": True, "message": ""}


def build_event(row_data: dict[str, str], months: int, label: str, due_months: int) -> dict:
    event_date = datetime.strptime(row_data["Event Date"], "%m/%d/%Y")
    reminder_date = event_date + relativedelta(months=months)
    due_date = event_date + relativedelta(months=due_months)
    date_str = reminder_date.strftime("%Y-%m-%d")

    return {
        "summary": (
            f"{row_data['Docket No.']} [{label}] | {row_data['Doc Code']} | "
            f"App {row_data['Application No.']} | Due {due_date.strftime('%b %d, %Y')}"
        ),
        "description": "\n".join([
            "PATENT DOCKET REMINDER",
            "=" * 40,
            f"Docket No.      : {row_data['Docket No.']}",
            f"Application No. : {row_data['Application No.']}",
            f"Doc Code        : {row_data['Doc Code']}",
            f"Particulars     : {row_data['Particulars']}",
            f"Mailroom Date   : {row_data['Event Date']}",
            f"Reminder        : {label} (Month +{months})",
            f"Reminder Date   : {reminder_date.strftime('%B %d, %Y')}",
            "=" * 40,
        ]),
        "start": {"date": date_str},
        "end": {"date": date_str},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 24 * 60},
                {"method": "popup", "minutes": 24 * 60},
            ],
        },
    }


def build_preview_rows(candidates: list[dict]) -> list[dict]:
    """One preview row per tracker entry (not per calendar reminder)."""
    preview_rows = []
    for candidate in candidates:
        rules = candidate["rules"]
        labels = ", ".join(rule[1] for rule in rules)
        first_event = build_event(candidate["row_data"], rules[0][0], rules[0][1], rules[0][2])
        preview_rows.append({
            "row_index": candidate["entry_id"],
            "docket_no": candidate["row_data"]["Docket No."],
            "application_no": candidate["row_data"]["Application No."],
            "doc_code": candidate["row_data"]["Doc Code"],
            "event_date": candidate["row_data"]["Event Date"],
            "reminder_count": len(rules),
            "reminders": labels,
            "first_reminder_date": first_event["start"]["date"],
            "summary": first_event["summary"],
        })
    return preview_rows


def _reminder_event_count(candidates: list[dict]) -> int:
    return sum(len(candidate["rules"]) for candidate in candidates)


def create_events_for_candidates(
    service, candidates: list[dict], *, job=None
) -> tuple[list[dict], list[dict]]:
    total = len(candidates)
    created_rows = []
    failed_rows = []

    for index, candidate in enumerate(candidates, start=1):
        entry_id = candidate["entry_id"]
        row_data = candidate["row_data"]
        docket = row_data.get("Docket No.", "")
        doc_code = row_data.get("Doc Code", "")
        if job is not None:
            from app.us_pto.jobs import update_job_progress

            update_job_progress(
                job,
                (index - 1) / max(total, 1),
                f"Creating calendar events ({index}/{total}): {docket} · {doc_code}",
            )
        print(f"Creating events for entry {entry_id} ({index}/{total})")
        created_ids = []
        created_labels = []

        try:
            for months, label, due_months in candidate["rules"]:
                event_body = build_event(candidate["row_data"], months, label, due_months)
                result = service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
                created_ids.append(result["id"])
                created_labels.append(label)

            event_ids_value = " | ".join(created_ids)
            update_entry(
                entry_id,
                calendar_event_ids=event_ids_value,
                calendar_status="Event Created with " + ", ".join(created_labels),
            )
            created_rows.append({
                "entry_id": entry_id,
                "docket_no": candidate["row_data"]["Docket No."],
                "application_no": candidate["row_data"]["Application No."],
                "doc_code": candidate["row_data"]["Doc Code"],
                "particulars": candidate["row_data"]["Particulars"],
                "event_date": candidate["row_data"]["Event Date"],
                "reminders": ", ".join(created_labels),
                "calendar_event_ids": event_ids_value,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception as exc:
            failed_rows.append({
                "entry_id": entry_id,
                "docket_no": candidate["row_data"]["Docket No."],
                "doc_code": candidate["row_data"]["Doc Code"],
                "error": str(exc),
            })

    return created_rows, failed_rows


def get_creation_candidates_for_ui(duplicate_mode: str) -> dict:
    init_db()
    creation_candidates = list_calendar_candidates(duplicate_mode=duplicate_mode)
    candidate_count = len(creation_candidates)
    return {
        "duplicate_mode": duplicate_mode,
        "candidate_count": candidate_count,
        "event_count": candidate_count,
        "reminder_event_count": _reminder_event_count(creation_candidates),
        "preview_rows": build_preview_rows(creation_candidates),
    }


def create_events_for_ui(duplicate_mode: str, *, job=None) -> dict:
    init_db()
    creation_candidates = list_calendar_candidates(duplicate_mode=duplicate_mode)
    if not creation_candidates:
        return {
            "status": "info",
            "message": "No new matching doc codes found for calendar creation.",
            "created_rows": [],
            "failed_rows": [],
            "candidate_count": 0,
            "event_count": 0,
            "reminder_event_count": 0,
            "appended_count": 0,
        }

    if job is not None:
        from app.us_pto.jobs import update_job_progress

        update_job_progress(
            job,
            0.0,
            f"Authorizing calendar — {len(creation_candidates)} row(s) to process…",
        )
    service = get_calendar_service()
    created_rows, failed_rows = create_events_for_candidates(
        service, creation_candidates, job=job
    )
    if job is not None:
        from app.us_pto.jobs import update_job_progress

        update_job_progress(job, 0.95, "Updating master sheet backup…")
    appended_count = append_backup_rows(HTML_BACKUP_FILE, created_rows)

    candidate_count = len(creation_candidates)
    return {
        "status": "success" if not failed_rows else "partial",
        "message": "events created successfully",
        "created_rows": created_rows,
        "failed_rows": failed_rows,
        "candidate_count": candidate_count,
        "event_count": candidate_count,
        "reminder_event_count": _reminder_event_count(creation_candidates),
        "appended_count": appended_count,
    }


def backup_row_key(row: dict) -> str:
    return "|".join([
        normalize_doc_code(row["doc_code"]),
        normalize_cell_value(row["event_date"]),
        normalize_cell_value(row["docket_no"]).upper(),
    ])


def read_existing_backup_keys(output_path: str) -> set[str]:
    if not os.path.exists(output_path):
        return set()
    with open(output_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
    return set(match.group(1) for match in re.finditer(r'data-key="([^"]+)"', content))


def ensure_backup_html_skeleton(output_path: str) -> None:
    if os.path.exists(output_path):
        return
    html = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Master Sheet Backup Ledger</title>",
        "<style>body{font-family:Arial,sans-serif;margin:16px;}table{border-collapse:collapse;width:100%;}",
        "th,td{border:1px solid #ccc;padding:8px;text-align:left;vertical-align:top;}th{background:#f4f4f4;}</style>",
        "</head><body><h2>Master Sheet Backup Ledger</h2><table><thead><tr>",
        "<th>Docket No.</th><th>Application No.</th><th>Doc Code</th><th>Particulars</th>",
        "<th>Event Date</th><th>Reminder Labels</th><th>Calendar Event IDs</th><th>Created At</th>",
        "</tr></thead><tbody></tbody></table></body></html>",
    ]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file_handle:
        file_handle.write("\n".join(html))


def append_backup_rows(output_path: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    ensure_backup_html_skeleton(output_path)
    existing_keys = read_existing_backup_keys(output_path)
    row_html = []
    appended_count = 0
    for row in rows:
        key = backup_row_key(row)
        if key in existing_keys:
            continue
        row_html.append(
            "<tr data-key=\"{key}\"><td>{docket_no}</td><td>{application_no}</td><td>{doc_code}</td>"
            "<td>{particulars}</td><td>{event_date}</td><td>{reminders}</td>"
            "<td>{calendar_event_ids}</td><td>{created_at}</td></tr>".format(
                key=escape(key, quote=True),
                docket_no=escape(row["docket_no"]),
                application_no=escape(row["application_no"]),
                doc_code=escape(row["doc_code"]),
                particulars=escape(row["particulars"]),
                event_date=escape(row["event_date"]),
                reminders=escape(row["reminders"]),
                calendar_event_ids=escape(row["calendar_event_ids"]),
                created_at=escape(row["created_at"]),
            )
        )
        existing_keys.add(key)
        appended_count += 1
    if not row_html:
        return 0
    with open(output_path, encoding="utf-8") as file_handle:
        content = file_handle.read()
    updated_content = content.replace("</tbody>", "\n".join(row_html) + "\n</tbody>", 1)
    with open(output_path, "w", encoding="utf-8") as file_handle:
        file_handle.write(updated_content)
    return appended_count
