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
    ITEM_FORM3_UPDATED: ("Form 3 with FER compliance", "Rule 12(2)"),
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


# --- Form 27 (Statement of Working) --------------------------------------
#
# Section 146(2) + Rule 131(2), Patents Rules 2003, as amended by the
# Patents (Amendment) Rules 2024.
#
# - Filed once every 3 financial years (Indian FY: 1 April - 31 March), not
#   annually (that was the pre-2024 position).
# - The reporting block starts from the FY immediately after the FY of grant.
# - Due date = 6 months after the block ends = 30 September following the
#   close of the third FY in the block.
# - Unlike the four one-time filing-formality items above, Form 27 recurs
#   for the life of the patent - each cycle is its own docket_entry row
#   (item_type keyed by the block's starting FY, e.g. "form27_2023"), not a
#   single row updated in place, so the filing history stays auditable.

FORM27_RULE_REFERENCE = "Section 146(2) / Rule 131(2)"
ITEM_FORM27_PREFIX = "form27_"

# Transitional rule (source: IPO's official Form 27 FAQ, 26 August 2024):
# patents granted in FY 2022-23 or earlier don't get the plain "grant + 1 FY"
# formula - it would predate the amended rule's own commencement. Instead,
# ALL such patents share one fixed first block. This is a one-time historical
# accommodation tied to the 2024 amendment, not a general rule - if IPO
# issues further transitional guidance later, re-check the source before
# extending this branch.
FORM27_TRANSITIONAL_CUTOFF_FY_START_YEAR = 2022
FORM27_TRANSITIONAL_BLOCK_START = 2023
FORM27_TRANSITIONAL_BLOCK_END = 2025
FORM27_TRANSITIONAL_FIRST_DUE_DATE = date(2026, 9, 30)


def _financial_year_start_year(d: date) -> int:
    """Indian FY runs 1 Apr - 31 Mar. Returns the calendar year the FY starts
    in, e.g. 31 Mar 2026 -> FY2025-26 -> 2025; 1 Apr 2026 -> FY2026-27 -> 2026."""
    return d.year if d.month >= 4 else d.year - 1


def form27_item_type(block_start_year: int) -> str:
    return f"{ITEM_FORM27_PREFIX}{block_start_year}"


def parse_form27_block_start(item_type: str) -> int | None:
    if not item_type.startswith(ITEM_FORM27_PREFIX):
        return None
    try:
        return int(item_type[len(ITEM_FORM27_PREFIX):])
    except ValueError:
        return None


def _form27_title(grant_number: str, block_start_year: int, block_end_year: int) -> str:
    return (
        f"File Form 27 - Statement of Working for Patent No. {grant_number} "
        f"(FY {block_start_year}-{block_start_year + 1} "
        f"to FY {block_end_year}-{block_end_year + 1})"
    )


def plan_form27_first_entry(*, grant_date: date, grant_number: str) -> DocketEntryPlan:
    """Triggered whenever the grant date is entered or corrected on a project."""
    fy_start_year = _financial_year_start_year(grant_date)
    if fy_start_year <= FORM27_TRANSITIONAL_CUTOFF_FY_START_YEAR:
        block_start = FORM27_TRANSITIONAL_BLOCK_START
        block_end = FORM27_TRANSITIONAL_BLOCK_END
        due_date = FORM27_TRANSITIONAL_FIRST_DUE_DATE
    else:
        block_start = fy_start_year + 1
        block_end = fy_start_year + 3
        due_date = date(fy_start_year + 4, 9, 30)

    return DocketEntryPlan(
        item_type=form27_item_type(block_start),
        title=_form27_title(grant_number, block_start, block_end),
        rule_reference=FORM27_RULE_REFERENCE,
        due_date=due_date,
    )


def plan_form27_next_entry(
    *, grant_number: str, prior_block_start_year: int, prior_due_date: date
) -> DocketEntryPlan:
    """Roll-forward: called when the current cycle's Form 27 item is closed.
    Next block is +3 FYs, due date +3 years - repeats for as long as the
    patent is in force (caller is responsible for that gate)."""
    block_start = prior_block_start_year + 3
    block_end = block_start + 2
    due_date = date(prior_due_date.year + 3, prior_due_date.month, prior_due_date.day)
    return DocketEntryPlan(
        item_type=form27_item_type(block_start),
        title=_form27_title(grant_number, block_start, block_end),
        rule_reference=FORM27_RULE_REFERENCE,
        due_date=due_date,
    )
