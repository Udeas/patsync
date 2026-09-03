"""Auto-docketed Indian filing-formality deadlines.

Ground truth: Indian Patents Act 1970 + Patents Rules 2003, as amended by the
Patents (Amendment) Rules 2024.

| Item | Due date rule | Basis |
|---|---|---|
| Assignment / Proof of right | filing date + 6 months | Rule 10 |
| Power of Attorney (Form 26) | filing date + 3 months | Rule 135(1) |
| First Form 3 (foreign-filing statement) | filing date + 6 months | Rule 12(1A) |
| Priority document | filing date + 3 months (internal target) | Section 138(1) / Rule 21 |
| Updated Form 3 (post-FER) | FER date + 3 months | Rule 12(2) |

The priority-document item has no clean statutory "filing date + N months"
rule the way the other three do - it's legally triggered by the
Controller's request under Section 138(1) (Convention) or tied to the
31-month national phase deadline (PCT). It defaults to filing date + 3
months uniformly as a system default/internal proactive-docketing target
regardless of Convention vs. PCT - callers must tag it in the UI as an
internal target rather than a hard statutory deadline (`is_internal_target`).

Rule 10 (assignment) and Rule 12(1A) (Form 3) don't, by the letter of the
rules, exempt provisional applications - but per firm practice these
formalities are only tracked from complete-specification/convention/PCT
stage onward. The provisional exclusion below is a business-practice
choice, not a legal exemption.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .reminders import add_months

ITEM_ASSIGNMENT = "assignment"
ITEM_PRIORITY_DOCUMENT = "priority_document"
ITEM_POA = "poa"
ITEM_FORM3_FIRST = "form3_first"
ITEM_FORM3_UPDATED = "form3_updated"

PROVISIONAL_APPLICATION_TYPE = "Provisional Application"

_ITEM_META: dict[str, tuple[str, str]] = {
    ITEM_ASSIGNMENT: ("Assignment / Proof of right", "Rule 10"),
    ITEM_PRIORITY_DOCUMENT: ("Priority document", "Section 138(1) / Rule 21 (internal target)"),
    ITEM_POA: ("Power of Attorney (Form 26)", "Rule 135(1)"),
    ITEM_FORM3_FIRST: ("First Form 3 (foreign-filing statement)", "Rule 12(1A)"),
    ITEM_FORM3_UPDATED: ("File updated Form 3", "Rule 12(2)"),
}


@dataclass(frozen=True)
class DocketEntryPlan:
    item_type: str
    title: str
    rule_reference: str
    due_date: date
    is_internal_target: bool = False
    auto_satisfied: bool = False


def plan_default_docket_entries(
    *,
    application_type: str | None,
    filing_date: date | None,
    has_priority_claim: bool,
    proof_of_right_furnished: bool,
) -> list[DocketEntryPlan]:
    """Requirement 1: default action items at project creation.

    `filing_date` should be the project's Indian filing date
    (`PatentProject.in_application_date`) - for PCT national phase projects
    this already IS the national-phase entry date, not the international
    filing date, so no separate PCT branching is needed here.
    """
    if not filing_date or application_type == PROVISIONAL_APPLICATION_TYPE:
        return []

    plans: list[DocketEntryPlan] = []

    title, rule = _ITEM_META[ITEM_ASSIGNMENT]
    plans.append(
        DocketEntryPlan(
            item_type=ITEM_ASSIGNMENT,
            title=title,
            rule_reference=rule,
            due_date=add_months(filing_date, 6),
            # Item is still created (and audited) even when proof of right
            # was furnished with Form 1 at filing - it's just pre-satisfied.
            auto_satisfied=proof_of_right_furnished,
        )
    )

    if has_priority_claim:
        title, rule = _ITEM_META[ITEM_PRIORITY_DOCUMENT]
        plans.append(
            DocketEntryPlan(
                item_type=ITEM_PRIORITY_DOCUMENT,
                title=title,
                rule_reference=rule,
                due_date=add_months(filing_date, 3),
                is_internal_target=True,
            )
        )

    title, rule = _ITEM_META[ITEM_POA]
    plans.append(
        DocketEntryPlan(
            item_type=ITEM_POA,
            title=title,
            rule_reference=rule,
            due_date=add_months(filing_date, 3),
        )
    )

    title, rule = _ITEM_META[ITEM_FORM3_FIRST]
    plans.append(
        DocketEntryPlan(
            item_type=ITEM_FORM3_FIRST,
            title=title,
            rule_reference=rule,
            due_date=add_months(filing_date, 6),
        )
    )

    return plans


def plan_form3_updated_entry(fer_date: date) -> DocketEntryPlan:
    """Requirement 2: triggered whenever the FER date is entered/updated."""
    title, rule = _ITEM_META[ITEM_FORM3_UPDATED]
    return DocketEntryPlan(
        item_type=ITEM_FORM3_UPDATED,
        title=title,
        rule_reference=rule,
        due_date=add_months(fer_date, 3),
    )
