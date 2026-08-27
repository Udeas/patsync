"""Indian patent renewal ("annuity") fee schedule and calculations.

Legal basis (verified against Patents Rules, 2003, Rule 80 and the First
Schedule — not just the illustrative client email that inspired this
feature; see docs/superpowers/specs for the write-up):

- Renewal fees are payable from the 3rd year of the patent's term through
  the 20th (last) year, both anchored on the FILING DATE, regardless of
  when the patent is actually granted (Rule 80(1)).
- If a patent is granted more than 2 years after filing, every renewal fee
  that would already have fallen due by the grant date becomes payable
  within 3 months of the date of grant (Rule 80(1A)/(3)) - this is a
  distinct, one-off deadline, not a normal per-year renewal date.
- The fee table below is the "large entity" (standard) category rate,
  cross-checked against the current First Schedule. Concessional rates
  for natural person / startup / small entity are NOT modeled yet since
  the application has no applicant-category concept today (see
  FEE_SCHEDULES below for how to extend this later without redesigning
  the calculation engine).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Sequence

FIRST_RENEWAL_YEAR = 3
LAST_RENEWAL_YEAR = 20

# Renewal Year -> Applicable Fee Category -> Official Fee.
# Only the "standard" (large entity) category is populated today. Adding a
# concessional category later is just another key in FEE_SCHEDULES; nothing
# else in this module needs to change.
STANDARD_ENTITY_FEES: dict[int, int] = {
    **{year: 4_000 for year in range(3, 7)},  # 3rd-6th year
    **{year: 12_000 for year in range(7, 11)},  # 7th-10th year
    **{year: 24_000 for year in range(11, 16)},  # 11th-15th year
    **{year: 40_000 for year in range(16, 21)},  # 16th-20th year
}

FEE_SCHEDULES: dict[str, dict[int, int]] = {
    "standard": STANDARD_ENTITY_FEES,
}

DEFAULT_FEE_CATEGORY = "standard"

_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}


def ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = _ORDINAL_SUFFIXES.get(n % 10, "th")
    return f"{n}{suffix}"


def format_year_range(years: Sequence[int]) -> str:
    """'3rd Year' for a single year, '3rd-7th Year' for a contiguous range."""
    if not years:
        return ""
    lo, hi = min(years), max(years)
    if lo == hi:
        return f"{ordinal(lo)} Year"
    return f"{ordinal(lo)}–{ordinal(hi)} Year"


def _add_months(value: date, months: int) -> date:
    month = value.month + months
    year = value.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def renewal_year_date(filing_date: date, year: int) -> date:
    """Due date for a given renewal year: payable before expiry of the
    PRECEDING year (Rule 80(1)) - i.e. filing date + (year - 1) years.
    Year 3's fee is due at the filing date's 2nd anniversary, year 20's at
    the 19th anniversary, etc. Matches the worked example: filing
    24-Dec-2020 -> year 3 due 24-Dec-2022, year 20 due 24-Dec-2039.
    """
    target_year = filing_date.year + (year - 1)
    day = min(filing_date.day, calendar.monthrange(target_year, filing_date.month)[1])
    return date(target_year, filing_date.month, day)


def post_grant_payment_deadline(grant_date: date) -> date:
    """Rule 80(1A): 3 months from the date of grant."""
    return _add_months(grant_date, 3)


def validate_renewal_year(year: int) -> None:
    if year < FIRST_RENEWAL_YEAR or year > LAST_RENEWAL_YEAR:
        raise ValueError(
            f"Renewal year must be between {FIRST_RENEWAL_YEAR} and {LAST_RENEWAL_YEAR}"
        )


def fee_for_year(year: int, fee_category: str = DEFAULT_FEE_CATEGORY) -> int:
    validate_renewal_year(year)
    schedule = FEE_SCHEDULES.get(fee_category)
    if schedule is None:
        raise ValueError(f"Unknown fee category: {fee_category}")
    return schedule[year]


def compute_fee_for_years(years: Iterable[int], fee_category: str = DEFAULT_FEE_CATEGORY) -> int:
    return sum(fee_for_year(year, fee_category) for year in years)


def overdue_renewal_years(filing_date: date, as_of_date: date) -> list[int]:
    """Renewal years whose own due date has already passed by `as_of_date`."""
    return [
        year
        for year in range(FIRST_RENEWAL_YEAR, LAST_RENEWAL_YEAR + 1)
        if renewal_year_date(filing_date, year) <= as_of_date
    ]


def accumulated_due_years_at_grant(filing_date: date, grant_date: date) -> list[int]:
    """Renewal years bundled into the post-grant accumulated-fee action.

    Rule 80(1A) only kicks in when the patent is granted more than 2 years
    after filing (i.e. after year 3's own due date has passed) - otherwise
    there is nothing "accumulated" and the normal per-year schedule applies
    from grant onward. When it does apply, the accumulated batch is every
    year already strictly overdue by the grant date PLUS the single next
    (currently-running) year, matched against the worked example in the
    spec: filing 24-Dec-2020 + grant 13-Aug-2026 -> years 3-6 are strictly
    overdue (due dates 2022-2025), and year 7 (due 24-Dec-2026, not yet due)
    is still bundled in as the year the patent is presently living through -
    reproducing the reference "3rd-7th Year" accumulated notice exactly.
    """
    year3_due = renewal_year_date(filing_date, FIRST_RENEWAL_YEAR)
    if grant_date <= year3_due:
        return []
    overdue = overdue_renewal_years(filing_date, grant_date)
    next_year = max(overdue) + 1
    if next_year <= LAST_RENEWAL_YEAR:
        overdue.append(next_year)
    return overdue


def paid_till_year(paid_years: Iterable[int]) -> int | None:
    """Highest year Y such that every year from 3..Y has been paid (no gaps)."""
    paid = set(paid_years)
    result: int | None = None
    year = FIRST_RENEWAL_YEAR
    while year in paid:
        result = year
        year += 1
    return result


def next_unpaid_year(paid_years: Iterable[int]) -> int:
    """First renewal year (from 3) not yet paid, contiguously."""
    till = paid_till_year(paid_years)
    return (till + 1) if till is not None else FIRST_RENEWAL_YEAR


def paid_till_date(filing_date: date, paid_years: Iterable[int]) -> date | None:
    """Date through which the patent is maintained: paying year N keeps the
    patent alive through year N's period, which runs until year (N+1)'s own
    due date - so "Paid Till" is the NEXT unpaid year's due date, not the
    last paid year's own due date. Matches the worked example: paying
    3rd-7th year -> Paid Till 24-Dec-2027 (year 8's due date), not
    24-Dec-2026 (year 7's own due date).
    """
    if paid_till_year(paid_years) is None:
        return None
    return renewal_year_date(filing_date, next_unpaid_year(paid_years))


def orphaned_paid_years(paid_years: Iterable[int]) -> list[int]:
    """Paid years that sit beyond a gap after the contiguous paid-till run.

    Normally empty. Only non-empty if a payment was recorded for a later
    year while an earlier year in between was never paid, or if a Filing
    Date edit reshuffled the schedule under an existing payment - surfaced
    to the UI as a conflict to review rather than silently hidden.
    """
    till = paid_till_year(paid_years)
    contiguous_end = till if till is not None else FIRST_RENEWAL_YEAR - 1
    return sorted(y for y in set(paid_years) if y > contiguous_end)


@dataclass(frozen=True)
class AnnuityAction:
    message: str
    due_date: date
    years: list[int] = field(default_factory=list)
    is_post_grant_deadline: bool = False


def compute_next_annuity_action(
    filing_date: date | None,
    grant_date: date | None,
    paid_years: Iterable[int] = (),
) -> AnnuityAction | None:
    """Next renewal-fee action to surface once a patent is granted.

    Mirrors compute_next_patent_action's contract (message + due_date) so it
    slots into the existing due_action/action_due_date pipeline unchanged.
    """
    if not filing_date or not grant_date:
        return None

    paid = set(paid_years)

    if not paid:
        accumulated = [y for y in accumulated_due_years_at_grant(filing_date, grant_date) if y not in paid]
        if accumulated:
            return AnnuityAction(
                message=f"Accumulated Renewal Fee — {format_year_range(accumulated)}",
                due_date=post_grant_payment_deadline(grant_date),
                years=accumulated,
                is_post_grant_deadline=True,
            )

    next_year = next_unpaid_year(paid)
    if next_year > LAST_RENEWAL_YEAR:
        return None
    return AnnuityAction(
        message=f"Renewal Fee Due — {format_year_range([next_year])}",
        due_date=renewal_year_date(filing_date, next_year),
        years=[next_year],
        is_post_grant_deadline=False,
    )
