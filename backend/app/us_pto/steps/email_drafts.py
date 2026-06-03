from __future__ import annotations

import base64
import re
from datetime import datetime

from dateutil.relativedelta import relativedelta
from email.message import EmailMessage

from app.us_pto.auth.gmail import get_gmail_service
from app.us_pto.doc_codes import get_email_template_for_code
from app.us_pto.email_templates import DOC_CODE_TEMPLATES
from app.us_pto.repository import init_db, list_draft_candidates, update_entry


def _template_for_entry(entry: dict) -> dict | None:
    template_key = get_email_template_for_code(entry.get("doc_code", ""))
    if not template_key:
        return None
    return DOC_CODE_TEMPLATES.get(template_key)

OPTIONAL_TEMPLATE_DEFAULTS = {
    "title": "",
    "filing_date": "",
    "rip_matter_id": "",
    "notice_issued_on": "",
    "allowed_claims": "",
    "issue_fee_amount": "",
    "issue_fee_deadline": "",
    "ctfr_due_date": "",
    "ctfr_extension_due_date": "",
    "ntc_miss_prt_due_date": "",
    "required_response_time": (
        "Written instructions and payment method must be received at least 14 days prior to the deadline."
    ),
    "attachments_html": (
        "<li>Notice of Allowance and Fees Due</li>"
        "<li>Copy of allowed claims</li>"
    ),
    "salutation": "Dear Sir/Madam,",
}


def normalize_doc_code(value) -> str:
    return str(value or "").strip().upper()


def normalize_cell_value(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%m/%d/%Y")
    return str(value).strip()


def get_master_file_lock_status() -> dict:
    return {"is_ready": True, "message": ""}


def build_row_context(entry: dict) -> dict[str, str]:
    context = {
        "docket_no": entry["docket_no"],
        "application_no": entry["application_no"],
        "doc_code": normalize_doc_code(entry["doc_code"]),
        "particulars": entry["particulars"],
        "event_date": entry["event_date"],
    }
    context.update(OPTIONAL_TEMPLATE_DEFAULTS)

    if context["doc_code"] == "NOA" and context["event_date"]:
        try:
            event_date = datetime.strptime(context["event_date"], "%m/%d/%Y")
            context["issue_fee_deadline"] = (event_date + relativedelta(months=3)).strftime("%B %d, %Y")
        except ValueError:
            pass

    if context["doc_code"] in {"CTFR", "CTNF"} and context["event_date"]:
        try:
            event_date = datetime.strptime(context["event_date"], "%m/%d/%Y")
            context["ctfr_due_date"] = (event_date + relativedelta(months=3)).strftime("%B %d, %Y")
            context["ctfr_extension_due_date"] = (event_date + relativedelta(months=6)).strftime("%B %d, %Y")
        except ValueError:
            pass

    if context["doc_code"] == "NTC.MISS.PRT" and context["event_date"]:
        try:
            event_date = datetime.strptime(context["event_date"], "%m/%d/%Y")
            context["ntc_miss_prt_due_date"] = (event_date + relativedelta(months=2)).strftime("%B %d, %Y")
        except ValueError:
            pass

    return context


def looks_like_html(content: str) -> bool:
    return bool(re.search(r"<[^>]+>", content))


def create_draft(service, subject: str, body: str) -> str:
    message = EmailMessage()
    message["Subject"] = subject
    if looks_like_html(body):
        plain_fallback = re.sub(r"<[^>]+>", "", body).strip() or "Please view this email in HTML format."
        message.set_content(plain_fallback)
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)

    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": encoded_message}},
    ).execute()
    return draft["id"]


def process_entries(entries: list[dict], service, *, job=None) -> tuple[int, int, int]:
    created_count = 0
    done_count = 0
    not_required_count = 0
    total = len(entries)

    for index, entry in enumerate(entries, start=1):
        context = build_row_context(entry)
        template = _template_for_entry(entry)
        docket = context.get("docket_no", "")
        doc_code = context.get("doc_code", "")

        if job is not None:
            from app.us_pto.jobs import update_job_progress

            update_job_progress(
                job,
                (index - 1) / max(total, 1),
                f"Processing draft ({index}/{total}): {docket} · {doc_code}",
            )

        if not template:
            update_entry(entry["id"], template_status="Not required")
            not_required_count += 1
            continue

        subject = template["subject"].format(**context)
        body = template["body"].format(**context)
        create_draft(service, subject, body)
        update_entry(entry["id"], template_status="Done")
        created_count += 1
        done_count += 1
        if job is not None:
            from app.us_pto.jobs import update_job_progress

            update_job_progress(
                job,
                index / max(total, 1),
                f"Created draft ({index}/{total}): {docket} · {doc_code}",
            )

    return created_count, done_count, not_required_count


def get_draft_candidates_for_ui() -> dict:
    init_db()
    candidates = list_draft_candidates()
    preview_rows = []
    not_required_candidates = 0

    for entry in candidates:
        context = build_row_context(entry)
        template = _template_for_entry(entry)
        if not template:
            continue
        preview_rows.append({
            "row_index": entry["id"],
            "docket_no": context["docket_no"],
            "application_no": context["application_no"],
            "doc_code": context["doc_code"],
            "subject": template["subject"].format(**context),
        })

    return {
        "draft_count": len(preview_rows),
        "not_required_count": not_required_candidates,
        "preview_rows": preview_rows,
    }


def create_drafts_for_ui(job=None) -> dict:
    init_db()
    candidates = list_draft_candidates()
    if job is not None:
        from app.us_pto.jobs import update_job_progress

        update_job_progress(
            job,
            0.0,
            f"Authorizing Gmail — {len(candidates)} row(s) to process…",
        )
    service = get_gmail_service()
    created_count, done_count, not_required_count = process_entries(
        candidates, service, job=job
    )
    return {
        "status": "success",
        "message": "Email draft creation completed.",
        "created_count": created_count,
        "done_count": done_count,
        "not_required_count": not_required_count,
    }
