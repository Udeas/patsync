from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlmodel import Session

from app.us_pto.database import get_us_pto_engine
from app.us_pto.email_templates import DOC_CODE_TEMPLATES
from app.us_pto.models import DocCodeRule, UsptoTracker

FINAL_DUE_MONTH_CHOICES = (1, 2, 3, 9, 12)
FINAL_DUE_EXTENSION_MONTH_CHOICES = (0, 1, 2, 3)


def _normalize_doc_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _ordinal(n: int) -> str:
    # Duplicated from doc_codes.py rather than imported: doc_codes.py needs to
    # import this module (to make doc-code-rule config authoritative there
    # too), so this module must not import doc_codes.py back or the two
    # would form a circular import.
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _init_db() -> None:
    # Deferred import: repository.py imports due_dates.py, which imports this
    # module at load time, so importing repository at module level here would
    # create a circular import. Deferring to call time avoids it.
    from app.us_pto.repository import init_db

    init_db()


def _validate_rule_input(
    doc_code: str,
    final_due_months: int,
    final_due_extension_months: int,
    email_template: str | None,
) -> tuple[str, str | None]:
    normalized = _normalize_doc_code(doc_code)
    if not normalized:
        raise ValueError("doc_code cannot be empty")
    if final_due_months not in FINAL_DUE_MONTH_CHOICES:
        raise ValueError(f"final_due_months must be one of {FINAL_DUE_MONTH_CHOICES}")
    if final_due_extension_months not in FINAL_DUE_EXTENSION_MONTH_CHOICES:
        raise ValueError(
            f"final_due_extension_months must be one of {FINAL_DUE_EXTENSION_MONTH_CHOICES}"
        )
    template_key = None
    if email_template and str(email_template).strip():
        template_key = str(email_template).strip().upper()
        if template_key not in DOC_CODE_TEMPLATES:
            raise ValueError(
                f"unknown email_template '{template_key}'; valid keys: "
                f"{', '.join(sorted(DOC_CODE_TEMPLATES.keys()))}"
            )
    return normalized, template_key


def get_doc_code_rule(doc_code: str) -> DocCodeRule | None:
    normalized = _normalize_doc_code(doc_code)
    if not normalized:
        return None
    _init_db()
    with Session(get_us_pto_engine()) as session:
        return session.scalars(
            select(DocCodeRule).where(DocCodeRule.doc_code == normalized)
        ).first()


def list_doc_code_rules() -> list[DocCodeRule]:
    _init_db()
    with Session(get_us_pto_engine()) as session:
        return list(
            session.scalars(select(DocCodeRule).order_by(DocCodeRule.doc_code)).all()
        )


def list_doc_codes_in_use() -> list[str]:
    _init_db()
    with Session(get_us_pto_engine()) as session:
        rows = session.scalars(select(UsptoTracker.doc_code).distinct()).all()
    return sorted({_normalize_doc_code(code) for code in rows if code})


def create_doc_code_rule(
    doc_code: str,
    final_due_months: int,
    final_due_extension_months: int,
    email_template: str | None = None,
) -> DocCodeRule:
    normalized, template_key = _validate_rule_input(
        doc_code, final_due_months, final_due_extension_months, email_template
    )
    _init_db()
    with Session(get_us_pto_engine()) as session:
        existing = session.scalars(
            select(DocCodeRule).where(DocCodeRule.doc_code == normalized)
        ).first()
        if existing:
            raise ValueError(f"a rule already exists for doc code {normalized}")
        rule = DocCodeRule(
            doc_code=normalized,
            final_due_months=final_due_months,
            final_due_extension_months=final_due_extension_months,
            email_template=template_key,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        return rule


def build_calendar_reminder_rules(rule: DocCodeRule) -> list[tuple[int, str, int]]:
    """(month_offset, label, due_month_offset) tuples for Step 2 calendar events.

    due_month_offset is final_due_months for every rule, initial or
    extension - by spec every reminder in the X+Y sequence surfaces the same
    Final Due Date in its title, not its own reminder date.
    """
    rules: list[tuple[int, str, int]] = []
    for month in range(1, rule.final_due_months + 1):
        rules.append((month, f"{_ordinal(month)} Month", rule.final_due_months))
    for extension_index in range(1, rule.final_due_extension_months + 1):
        month_offset = rule.final_due_months + extension_index
        rules.append(
            (month_offset, f"{_ordinal(extension_index)} Month Extension", rule.final_due_months)
        )
    return rules


def delete_doc_code_rule(doc_code: str) -> bool:
    normalized = _normalize_doc_code(doc_code)
    _init_db()
    with Session(get_us_pto_engine()) as session:
        rule = session.scalars(
            select(DocCodeRule).where(DocCodeRule.doc_code == normalized)
        ).first()
        if not rule:
            return False
        session.delete(rule)
        session.commit()
        return True
