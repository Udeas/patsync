from __future__ import annotations

import email
import imaplib
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from app.us_pto.config import IMAP_HOST, IMAP_MAILBOX, IMAP_PASSWORD, IMAP_USERNAME
from app.us_pto.doc_codes import is_tracked_doc_code


def get_html_body(msg) -> str | None:
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return None


def get_plain_body(msg) -> str:
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def parse_subject_fields(subject: str) -> tuple[str, str]:
    application_no = ""
    docket_no = ""
    if not subject:
        return application_no, docket_no

    app_match = re.search(r"App\s+(\d+)", subject, re.I)
    if app_match:
        application_no = app_match.group(1).strip()

    docket_match = re.search(r",\s*ADN\s+(.+?)(?:\s*$)", subject, re.I)
    if docket_match:
        docket_no = docket_match.group(1).strip()
    return application_no, docket_no


def parse_plain_text_fields(text: str) -> dict[str, str]:
    if not text:
        return {}

    fields: dict[str, str] = {}
    app_match = re.search(r"Application\s+Number:\s*(\d+)", text, re.I)
    if app_match:
        fields["application_no"] = app_match.group(1).strip()

    docket_match = re.search(
        r"Attorney\s+Docket\s+No\.?:\s*([^\s\r\n]+)", text, re.I
    )
    if docket_match:
        fields["docket_no"] = docket_match.group(1).strip()

    client_match = re.search(r"^Client:\s*(.+)$", text, re.I | re.M)
    if client_match:
        fields["client"] = client_match.group(1).strip()

    return fields


def _office_action_section(soup: BeautifulSoup) -> Tag | None:
    header = soup.find(string=re.compile(r"OFFICE\s+ACTION\s+EMAIL\s+DETAILS", re.I))
    if not header:
        return None
    node = header.find_parent("td") or header.find_parent("tr")
    if not node:
        return None
    for parent in node.parents:
        if parent.name == "table":
            return parent
    return node


def _cell_is_field_label(text: str, label_pattern: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    return bool(re.fullmatch(rf"{label_pattern}\s*:?", cleaned, re.I))


def _field_from_row(tr: Tag, label_pattern: str) -> str:
    tds = tr.find_all("td", recursive=False) or tr.find_all("td")
    for index, td in enumerate(tds):
        label_text = td.get_text(" ", strip=True)
        if not _cell_is_field_label(label_text, label_pattern):
            continue
        if index + 1 < len(tds):
            return tds[index + 1].get_text(" ", strip=True)
        sibling = td.find_next_sibling("td")
        if sibling:
            return sibling.get_text(" ", strip=True)
    return ""


def find_field_in_scope(scope: Tag | BeautifulSoup, label_pattern: str) -> str:
    for tr in scope.find_all("tr"):
        value = _field_from_row(tr, label_pattern)
        if value:
            return value
    return ""


def _parse_doc_code_table(scope: Tag | BeautifulSoup) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    header_tr = None
    for tr in scope.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if not cells:
            continue
        first = cells[0].strip()
        if re.fullmatch(r"Code", first, re.I):
            header_tr = tr
            break

    if not header_tr:
        code_header = scope.find(string=re.compile(r"^Code$", re.I))
        if code_header:
            header_tr = code_header.find_parent("tr")

    if not header_tr:
        return rows

    for tr in header_tr.find_next_siblings("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        code = tds[0].get_text(" ", strip=True)
        if not code or re.search(r"UPDATES\s+TO\s+DOCKETTRAK", code, re.I):
            break
        description = "".join(
            child.get_text(" ", strip=True)
            for child in tds[1].children
            if isinstance(child, NavigableString)
        ).strip() or tds[1].get_text(" ", strip=True)
        event_date = tds[2].get_text(" ", strip=True)
        if code:
            rows.append(
                {
                    "doc_code": code,
                    "particulars": description,
                    "event_date": event_date,
                }
            )
    return rows


def parse_office_action(html: str, *, subject: str = "", plain_text: str = "") -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    section = _office_action_section(soup) or soup

    application_no = find_field_in_scope(section, r"Application\s+Number")
    docket_no = find_field_in_scope(section, r"Attorney\s+Docket\s+No")
    client = find_field_in_scope(section, r"Client")

    subject_app, subject_docket = parse_subject_fields(subject)
    if not application_no:
        application_no = subject_app
    if not docket_no:
        docket_no = subject_docket

    plain_fields = parse_plain_text_fields(plain_text)
    application_no = application_no or plain_fields.get("application_no", "")
    docket_no = docket_no or plain_fields.get("docket_no", "")
    client = client or plain_fields.get("client", "")

    doc_rows = _parse_doc_code_table(section)
    if not doc_rows:
        doc_rows = _parse_doc_code_table(soup)

    rows = []
    for doc_row in doc_rows:
        rows.append(
            {
                "Docket No.": docket_no,
                "Application No.": application_no,
                "Client": client,
                "Doc Code": doc_row["doc_code"],
                "Particulars": doc_row["particulars"],
                "Event Date": doc_row["event_date"],
            }
        )
    return rows


def parsed_rows_for_api(rows: list[dict]) -> list[dict]:
    api_rows = []
    for row in rows:
        doc_code = row.get("Doc Code", "")
        api_rows.append(
            {
                "docket_no": row.get("Docket No.", ""),
                "application_no": row.get("Application No.", ""),
                "client": row.get("Client", ""),
                "doc_code": doc_code,
                "particulars": row.get("Particulars", ""),
                "event_date": row.get("Event Date", ""),
                "is_tracked": is_tracked_doc_code(doc_code),
            }
        )
    return api_rows


def _select_mailbox(imap: imaplib.IMAP4_SSL) -> bool:
    status, _ = imap.select(IMAP_MAILBOX, readonly=False)
    if status == "OK":
        return True
    _, mailboxes = imap.list()
    found = None
    for mailbox in mailboxes or []:
        mailbox_str = mailbox.decode() if isinstance(mailbox, bytes) else str(mailbox)
        if IMAP_MAILBOX in mailbox_str:
            matches = re.findall(r'"(.+)"$', mailbox_str)
            if matches:
                found = matches[0]
                break
    if found:
        imap.select(found, readonly=False)
        return True
    print(f"Mailbox '{IMAP_MAILBOX}' not found.")
    return False


def fetch_emails(job=None) -> tuple[list[dict], int]:
    return _fetch_emails_matching("UNSEEN", "unseen message(s)", job=job)


def fetch_emails_since(since_date, job=None) -> tuple[list[dict], int]:
    """Rebuild-from-scratch scan: every message in the mailbox received on or
    after since_date (a date/datetime), regardless of its \\Seen flag. Unlike
    fetch_emails() (which only ever looks at UNSEEN mail for incremental
    day-to-day polling), this is meant for re-importing a date range after
    the docket table has been cleared, since by then everything in the
    mailbox is already marked \\Seen from prior runs."""
    criteria = f'(SINCE "{since_date.strftime("%d-%b-%Y")}")'
    return _fetch_emails_matching(
        criteria, f"message(s) since {since_date.isoformat()}", job=job
    )


def _fetch_emails_matching(search_criteria: str, description: str, job=None) -> tuple[list[dict], int]:
    if not IMAP_USERNAME or not IMAP_PASSWORD:
        raise RuntimeError(
            "Email credentials not configured. Set US_PTO_IMAP_USERNAME and US_PTO_IMAP_PASSWORD."
        )

    # Without a timeout the underlying socket blocks forever on any stalled
    # server response (e.g. logout()) - bounding it turns a silent hang into
    # a catchable socket.timeout.
    imap = imaplib.IMAP4_SSL(IMAP_HOST, timeout=30)
    imap.login(IMAP_USERNAME, IMAP_PASSWORD)

    if not _select_mailbox(imap):
        imap.logout()
        return [], 0

    _, message_ids = imap.search(None, search_criteria)
    ids = message_ids[0].split()
    if not ids:
        print(f"No {description} found.")
        imap.logout()
        return [], 0

    total = len(ids)
    print(f"Found {total} {description}.")
    all_rows = []
    unparsed_count = 0
    seen_mark_failures = 0

    for index, num in enumerate(ids, start=1):
        mid = num.decode() if isinstance(num, bytes) else str(num)
        # BODY.PEEK[] (unlike plain RFC822) never implicitly sets \Seen as a
        # side effect of fetching - marking-as-seen below is the only place
        # that happens, so we can gate it on parse success.
        _, raw = imap.fetch(mid, "(BODY.PEEK[])")
        parsed_ok = False
        for part in raw:
            if isinstance(part, tuple):
                msg = email.message_from_bytes(part[1])
                html = get_html_body(msg)
                subject = msg.get("Subject", "(no subject)")
                plain = get_plain_body(msg)
                if job is not None:
                    from app.us_pto.jobs import update_job_progress

                    update_job_progress(
                        job,
                        (index - 1) / max(total, 1),
                        f"Processing email {index}/{total}: {subject}",
                    )
                if html:
                    rows = parse_office_action(html, subject=subject, plain_text=plain)
                    if rows:
                        print(f"  Parsed {subject}: {len(rows)} row(s)")
                        all_rows.extend(rows)
                        parsed_ok = True
                        if job is not None:
                            from app.us_pto.jobs import update_job_progress

                            update_job_progress(
                                job,
                                index / max(total, 1),
                                f"Parsed {len(rows)} row(s) from: {subject}",
                            )
                    else:
                        print(f"  Skipped {subject}: No OFFICE ACTION EMAIL DETAILS found")
                else:
                    print(f"  Skipped {subject}: No HTML body found")

        if parsed_ok:
            status, _ = imap.store(mid, "+FLAGS", "\\Seen")
            if status != "OK":
                seen_mark_failures += 1
                print(f"  Warning: failed to mark message {mid} as read (status={status})")
        else:
            # Leave unparsed messages unseen so they surface again on the next
            # run instead of being silently and permanently discarded.
            unparsed_count += 1

    imap.logout()
    if unparsed_count:
        print(
            f"{unparsed_count} message(s) left unread - could not find a recognizable "
            "office-action table/HTML body. Review them manually."
        )
    if seen_mark_failures:
        print(f"{seen_mark_failures} message(s) failed to be marked as read.")
    return all_rows, unparsed_count


def save_rows_to_db(rows: list[dict]) -> tuple[int, int]:
    from app.us_pto.repository import init_db, insert_entries_from_rows

    init_db()
    return insert_entries_from_rows(rows)


def run_fetch_for_ui(job=None) -> dict:
    try:
        if job is not None:
            from app.us_pto.jobs import update_job_progress

            update_job_progress(job, 0.0, "Connecting to mailbox…")
        rows, unparsed_count = fetch_emails(job=job)
        parsed_count = len(rows)
        unparsed_suffix = (
            f" {unparsed_count} email(s) left unread - no recognizable office-action "
            "content found; review them manually."
            if unparsed_count
            else ""
        )
        if not rows:
            return {
                "status": "info",
                "message": ("No new email data extracted." + unparsed_suffix).strip(),
                "inserted_count": 0,
                "parsed_count": 0,
                "parsed_rows": [],
                "skipped_duplicates": 0,
                "unparsed_count": unparsed_count,
            }
        inserted, skipped_duplicates = save_rows_to_db(rows)
        if inserted == 0 and skipped_duplicates > 0:
            message = (
                f"Parsed {parsed_count} row(s); all were already in the database "
                f"({skipped_duplicates} duplicate(s))."
            )
            status = "info"
        else:
            message = (
                f"Parsed {parsed_count} row(s) and saved {inserted} new row(s)."
                + (
                    f" Skipped {skipped_duplicates} duplicate(s)."
                    if skipped_duplicates
                    else ""
                )
            )
            status = "success"
        message = (message + unparsed_suffix).strip()
        return {
            "status": status,
            "message": message,
            "inserted_count": inserted,
            "parsed_count": parsed_count,
            "parsed_rows": parsed_rows_for_api(rows),
            "skipped_duplicates": skipped_duplicates,
            "unparsed_count": unparsed_count,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
            "inserted_count": 0,
            "parsed_count": 0,
            "parsed_rows": [],
            "skipped_duplicates": 0,
            "unparsed_count": 0,
        }
