# Indian Patent Annuity / Renewal Fee Workflow

Implemented directly per the incoming task spec (inspect-first, no
up-front plan approval gate) — this doc records the design decisions,
legal verification, and one real discrepancy found against the task
spec's own worked example, for future reference.

## Legal verification (Patents Rules, 2003)

Per task requirement §18, verified against primary/authoritative sources
rather than trusting the client email at face value:

- **Rule 80(1)**: renewal fees run from the 3rd year of the patent's term
  through the 20th (last), anchored on the **filing date**, payable before
  expiry of the *preceding* year. So year N's due date = filing date +
  (N-1) years. (Caught and fixed an off-by-one here during implementation
  — see below.)
- **Rule 80(1A)/(3)**: if a patent is granted more than 2 years after
  filing, every renewal fee already fallen due by grant time is payable
  within **3 months of the grant date** — confirmed via multiple
  independent sources, matches the task spec's "Grant Date + 3 months"
  exactly.
- **Fee table**: the task's client-email numbers (₹4,000/8,000/12,000/
  24,000/40,000 tiers) independently cross-checked against the current
  First Schedule and confirmed to be the **"large entity" / standard**
  category rate. Concessional rates (natural person / startup / small
  entity) exist in the real schedule too but are NOT modeled here, since
  the application has no applicant-category concept today — the fee
  engine is structured (`FEE_SCHEDULES: dict[category, dict[year, fee]]`)
  so adding one later doesn't require redesigning anything.

## Two bugs caught by verifying against the worked example before writing tests

1. **Renewal-year date off-by-one.** Naively anchoring year N at filing +
   N years gives year 3 = filing + 3y. The spec's own table says year 3 =
   filing + 2y (24-Dec-2020 → 24-Dec-2022). Fixed to filing + (N-1) years.
2. **"Paid Till" anchor.** Naively, paying through year 7 → "Paid Till"
   = year 7's own due date. The spec's own example says paying 3rd–7th
   year → **Paid Till 24-Dec-2027**, which is year **8**'s due date, not
   year 7's (24-Dec-2026). Paying year N keeps the patent maintained
   *through* year N's period, which ends at year (N+1)'s due date. Fixed
   `paid_till_date()` to anchor on `next_unpaid_year`, not `paid_till_year`.

Both were caught by running the calculation against the E17-06IN worked
example ad hoc before locking in the test suite — the test suite then
encodes the corrected behavior.

## "Accumulated batch" rule (not itself a literal Rule 80 clause)

Rule 80(1A) only requires paying *already-overdue* years within 3 months
of grant. Under a strict reading, E17-06IN's example (filing 24-Dec-2020,
grant 13-Aug-2026) would have years 3–6 overdue (due dates 2022–2025) but
**not** year 7 (due 24-Dec-2026, after the grant). The task's own worked
example nonetheless bundles year 7 into the "3rd–7th Year" accumulated
notice. Reproduced this as: *accumulated batch = all strictly-overdue
years, plus the single next (currently-running) year* — a practical
patent-agent batching convention (pay the almost-due one along with the
overdue ones rather than a separate transaction 4 months later), not a
separate legal requirement. Implemented in
`accumulated_due_years_at_grant()` with this reasoning documented inline.

## Architecture

- **`app/patents/annuity.py`**: pure calculation engine (renewal-year
  dates, fee schedule, accumulated-batch rule, paid-till/next-unpaid,
  ordinal/range formatting). No DB access — fully unit-testable, and
  mirrored in the frontend (`patent-annuity.ts`) for the live payment-modal
  preview.
- **Data model**: `PatentAnnuityPayment` (one row per payment transaction:
  payment_date, total_fee) + `PatentAnnuityPaymentYear` (one row per
  renewal year that payment covers). A schedule/status-per-year table was
  deliberately **not** created — due dates, fees, and paid/unpaid status
  are fully deterministic from filing_date + fee table + which years have
  a payment row, so they're computed live on every read (same pattern the
  app already uses for `due_action`/`action_due_date` via
  `compute_next_patent_action`). This means editing Grant Date or Filing
  Date before/after payment "just works" — there's no cached schedule to
  invalidate, only the immutable payment history to preserve.
- **Reminders integration**: `compute_next_patent_action` special-cases
  `STATUS_ID_GRANTED` (previously a dead end / terminal status) to call
  `annuity.compute_next_annuity_action()` instead, so the existing
  due_action/action_due_date pipeline (dashboard, timeline) picks up the
  next annuity action with no separate plumbing.
- **Endpoints**: `GET /projects/{id}/annuity` (full summary: schedule,
  payment history, paid-till, next-due, accumulated batch, conflict flags)
  and `POST /projects/{id}/annuity/payments` (record a payment covering
  one or more years in one transaction; rejects any year already paid).
- **Frontend**: new "Annuity / Renewal Fees" panel on the patent detail
  page (shown once granted), year-by-year schedule table, payment history,
  and a payment modal with live fee/paid-till/next-due preview as years
  are checked/unchecked (client-side mirror of the calc engine, backend
  is authoritative on submit).

## Test coverage

- `tests/test_patent_annuity.py`: 13 tests, pure calc engine (dates, fees,
  accumulated batch, paid-till, next-unpaid, edge cases: granted within 2
  years, fully paid through year 20, orphaned/gap years).
- `tests/test_patent_annuity_service.py`: the spec's 7 numbered test
  scenarios end-to-end through the service layer, reproducing E17-06IN
  exactly (accumulated years, deadline, fee, paid-till, next-due,
  duplicate-year rejection, advance payment, grant-date-change
  recalculation, and payment-history preservation).
- `patent-annuity.spec.ts` + `patents-detail.component.spec.ts`: frontend
  calc mirror + panel/modal behavior (live preview, submit payload,
  already-paid years excluded from selection).

## Deliberately out of scope

- Applicant fee category (individual/startup/small/large entity) — no
  concept of this exists in the app yet; only the "standard" schedule is
  wired up, structured for easy extension.
- A dedicated "Filing Date changed after payment" conflict test — not in
  the spec's required test list; the underlying mechanism (live
  recomputation + `orphaned_paid_years` conflict surfacing) handles it,
  but wasn't given a dedicated regression test given the explicit scope of
  the 7 numbered tests.
