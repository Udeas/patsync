# Doc Code Calendar Events

**Status: implemented** for doc codes that have a rule in the "Manage Doc
Code Rules" table (`doc_code_rules`, `app/us_pto/doc_code_rules.py`). Doc
codes without a rule there still fall back to the legacy YAML
(`config/doc_codes.yaml`) profile, unchanged — see "Legacy fallback" below.
`DOCKET_EXCLUDED_DOC_CODES` (ABN) in `app/us_pto/repository.py` was left
untouched; ABN merges into the general logic automatically once someone adds
an ABN row to Manage Doc Code Rules and that hardcoded filter is removed —
that removal itself is still outstanding.

## Calendar Events Generation Process

**Trigger:** Step 2 of the Run Automation pipeline ("Create Google Calendar
events"), same as before — not automatic on docket create/update. Source:
`app/us_pto/repository.list_calendar_candidates()` →
`app/us_pto/steps/calendar_events.py`.

**Source Data:**
- Event Date: the docket's Event Date.
- Doc Code rule: Final Due Months (X) and Final Due Months with Extension
  (Y) from `doc_code_rules`.

**Rule (X + Y):** for a docket whose doc code has a rule with X initial
months and Y extension months, Step 2 creates **X + Y events**, one per
month, at 1-month intervals starting 1 month after the Event Date:

- Initial deadlines (months 1..X): title
  `<Docket No.> <Nth> Month | <Doc Code> | App <App No.> | Due <Fixed Deadline Date>`
- Extension deadlines (months X+1..X+Y): title
  `<Docket No.> <Nth> Month Extension | <Doc Code> | App <App No.> | Due <Fixed Deadline Date>`

The **Fixed Deadline Date** is the same for every event in the sequence —
Event Date + X months (the Final Due Date) — including the extension events.
This matches the existing legacy behavior (see below) and is intentional per
spec, not a bug: extension event titles show the Final Due Date, not their
own later date.

**Example — CTFR, rule 3+3, Event Date 2026-07-10:**

```
DOCKET-1 1st Month | CTFR | App APP-1 | Due Oct 10, 2026        (reminder 2026-08-10)
DOCKET-1 2nd Month | CTFR | App APP-1 | Due Oct 10, 2026        (reminder 2026-09-10)
DOCKET-1 3rd Month | CTFR | App APP-1 | Due Oct 10, 2026        (reminder 2026-10-10)
DOCKET-1 1st Month Extension | CTFR | App APP-1 | Due Oct 10, 2026  (reminder 2026-11-10)
DOCKET-1 2nd Month Extension | CTFR | App APP-1 | Due Oct 10, 2026  (reminder 2026-12-10)
DOCKET-1 3rd Month Extension | CTFR | App APP-1 | Due Oct 10, 2026  (reminder 2027-01-10)
```

This structure applies to any doc code rule, not just CTFR — e.g. a 2+4 rule
produces 2 initial + 4 extension events, a 1+5 rule produces 1 + 5, etc.
Implemented in `app/us_pto/doc_code_rules.build_calendar_reminder_rules()`.

**Save:** unchanged — each created event's Google Calendar event ID is
appended to the docket's `calendar_event_ids`, same as before.

## Legacy fallback (doc codes with no rule in `doc_code_rules`)

`list_calendar_candidates()` falls back to the pre-existing YAML
`calendar_profiles`/`tracked_doc_codes` config
(`app/us_pto/doc_codes.get_rules_for_tracked_doc_code`) for any doc code that
has no row in `doc_code_rules`. Titles keep the old bracketed format,
e.g. `DOCKET-2 [1st Month Deadline] | NOA | App APP-2 | Due Oct 10, 2026`.
No behavior changed for doc codes still only configured in
`config/doc_codes.yaml`.

## Notes

- Events are not generated for doc codes without any rule (new or legacy).
- Email templates (`config/doc_codes.yaml` → `email_template`, and the
  optional Email Template field on Manage Doc Code Rules) are unrelated to
  this and unchanged.
