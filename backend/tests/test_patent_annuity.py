"""Renewal ("annuity") fee calculation engine - the E17-06IN worked example
from the spec, reproduced exactly, plus the documented edge cases.
"""

from datetime import date

import pytest

from app.patents import annuity as a

FILING_DATE = date(2020, 12, 24)
GRANT_DATE = date(2026, 8, 13)


def test_renewal_year_dates_match_the_worked_schedule():
    # 3rd year due at filing + 2 years, 20th year due at filing + 19 years.
    assert a.renewal_year_date(FILING_DATE, 3) == date(2022, 12, 24)
    assert a.renewal_year_date(FILING_DATE, 4) == date(2023, 12, 24)
    assert a.renewal_year_date(FILING_DATE, 5) == date(2024, 12, 24)
    assert a.renewal_year_date(FILING_DATE, 6) == date(2025, 12, 24)
    assert a.renewal_year_date(FILING_DATE, 7) == date(2026, 12, 24)
    assert a.renewal_year_date(FILING_DATE, 20) == date(2039, 12, 24)


def test_post_grant_payment_deadline_is_three_months_from_grant():
    assert a.post_grant_payment_deadline(GRANT_DATE) == date(2026, 11, 13)


def test_e17_06in_accumulated_years_and_fee():
    accumulated = a.accumulated_due_years_at_grant(FILING_DATE, GRANT_DATE)
    assert accumulated == [3, 4, 5, 6, 7]
    assert a.format_year_range(accumulated) == "3rd–7th Year"
    assert a.compute_fee_for_years(accumulated) == 28_000


def test_e17_06in_next_annuity_action_before_any_payment():
    action = a.compute_next_annuity_action(FILING_DATE, GRANT_DATE, [])
    assert action is not None
    assert action.message == "Accumulated Renewal Fee — 3rd–7th Year"
    assert action.due_date == date(2026, 11, 13)
    assert action.years == [3, 4, 5, 6, 7]
    assert action.is_post_grant_deadline is True


def test_pay_3rd_to_7th_year():
    years = [3, 4, 5, 6, 7]
    assert a.compute_fee_for_years(years) == 28_000
    assert a.paid_till_date(FILING_DATE, years) == date(2027, 12, 24)
    assert a.next_unpaid_year(years) == 8


def test_pay_8th_to_10th_year_after_3rd_to_7th():
    already_paid = [3, 4, 5, 6, 7]
    new_years = [8, 9, 10]
    assert a.compute_fee_for_years(new_years) == 36_000
    all_paid = already_paid + new_years
    assert a.paid_till_date(FILING_DATE, all_paid) == date(2030, 12, 24)
    assert a.next_unpaid_year(all_paid) == 11


def test_next_annuity_action_after_partial_payment_uses_next_years_own_date_not_plus_one_year():
    # Critical rule: next reminder is NOT payment_date + 1 year, it's the
    # next unpaid renewal year's own date (from the filing date).
    paid = [3, 4, 5, 6, 7]
    action = a.compute_next_annuity_action(FILING_DATE, GRANT_DATE, paid)
    assert action is not None
    assert action.message == "Renewal Fee Due — 8th Year"
    # 8th year's own due date from the FILING date - not payment_date (13-Nov-2026) + 1 year.
    assert action.due_date == date(2027, 12, 24)
    assert action.due_date != date(2027, 11, 13)
    assert action.is_post_grant_deadline is False


def test_advance_payment_of_future_years_skips_them_in_next_reminder():
    # Selecting years beyond what's strictly due yet is allowed (advance
    # payment); the next reminder must skip all paid years.
    paid = [3, 4, 5, 6, 7, 8, 9]
    assert a.paid_till_date(FILING_DATE, paid) == date(2029, 12, 24)
    assert a.next_unpaid_year(paid) == 10


def test_fee_for_year_rejects_out_of_range_years():
    with pytest.raises(ValueError):
        a.fee_for_year(2)
    with pytest.raises(ValueError):
        a.fee_for_year(21)


def test_granted_within_two_years_of_filing_has_no_accumulated_batch():
    # Rule 80(1A) only applies when grant is LATER than 2 years post-filing.
    early_grant = date(2022, 6, 1)  # well within 2 years of FILING_DATE
    assert a.accumulated_due_years_at_grant(FILING_DATE, early_grant) == []
    action = a.compute_next_annuity_action(FILING_DATE, early_grant, [])
    assert action is not None
    assert action.message == "Renewal Fee Due — 3rd Year"
    assert action.is_post_grant_deadline is False
    assert action.due_date == date(2022, 12, 24)


def test_fully_paid_through_last_year_has_no_next_action():
    all_years = list(range(3, 21))
    assert a.next_unpaid_year(all_years) == 21
    action = a.compute_next_annuity_action(FILING_DATE, GRANT_DATE, all_years)
    assert action is None


def test_orphaned_paid_years_flags_a_gap():
    # Year 8 paid without year 7 in between - a real gap to surface, not
    # silently absorb into "paid till".
    paid_with_gap = [3, 4, 5, 6, 8]
    assert a.paid_till_year(paid_with_gap) == 6
    assert a.orphaned_paid_years(paid_with_gap) == [8]


def test_no_orphaned_years_for_a_clean_contiguous_run():
    assert a.orphaned_paid_years([3, 4, 5, 6, 7]) == []
