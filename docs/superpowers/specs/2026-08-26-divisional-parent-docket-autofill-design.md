# Divisional Parent-Docket Autofill

> **Revision note (2026-08-26):** this spec was corrected after initial
> implementation. The original version copied the parent's own IN
> application no/date directly onto the new (child) docket's own
> `in_application_no`/`in_application_date` fields. That was wrong — a
> divisional application is a distinct child application with its own
> application number/date, entered separately by the user. The parent's
> application no/date must instead be stored as a **separate "parent
> application" record** on the new docket, and certain date validations
> must be skipped for divisional-family types. This revision documents
> the corrected design; the "Implementation notes" / "Data model" /
> "Validation" sections below supersede the original.

## Problem

When creating a new Docket whose Application Type is a divisional type
(`Ordinary Divisional`, `Convention divisional`, `PCT National Phase Entry -
Divisional`), the user currently has to re-type application title,
applicants, inventors, and priority data that already exists on the parent
docket, and has no structured place to record the parent application's own
number/date (which differs from the new child docket's own application
number/date).

## Scope

- `frontend` repo: create-docket form changes.
- `patsync` repo: new DB columns + migration, schema changes, validation
  changes.
- No new endpoints.

## Concepts

- **Parent docket**: an existing Final Docket, picked via a typeahead, used
  purely as a data source to copy from. Selecting one does **not** create
  any operational dependency at runtime beyond the copy + the stored
  reference described below.
- **Child docket** (the one being created): a divisional/convention-
  divisional/PCT-divisional application. It has its **own**
  `in_application_no` / `in_application_date`, entered separately by the
  user — these are never auto-filled from the parent.
- **Parent application no/date**: the parent docket's own
  `in_application_no` / `in_application_date` at the time it was picked,
  copied once into two new columns on the child docket row
  (`parent_application_no`, `parent_application_date`). This is historical
  reference data on the child, not a live join.

## Trigger

- Only in **create mode** of `PatentsCreateComponent` (not edit mode).
- Only when `application_type` is one of the 3 divisional types (matched by
  exact membership in a `DIVISIONAL_APPLICATION_TYPES` set — not a loose
  substring match — to avoid ambiguity if similarly-named types are added
  later).
- Applies regardless of Docket Type (`project_mode`, Draft or Final).

## UI (frontend)

- Parent-docket picker: unchanged from the original spec — native
  `<input list>` + `<datalist>` typeahead, positioned before
  `APPLICATION TITLE`, options labeled `"{client_code} - {docket_no}"`,
  sourced from a lazy-loaded, client-side-filtered (`project_mode ===
  'final'`) call to `GET /api/patents/projects?include_archived=false`.
- New: two **read-only** fields, "Parent Application No." and "Parent
  Application Date", shown only when the divisional trigger is active,
  bound to new form controls `parent_application_no` /
  `parent_application_date`. Populated from the selected parent's own
  `in_application_no` / `in_application_date` on selection; not
  user-editable (disabled inputs).
- The existing "IN Application No." / "IN Application Date" fields
  (the child's own) are **left untouched** by parent selection — no
  autofill into them. User fills them in separately, same as any other
  application type.
- `application_title`, `applicants`, `inventors`, `conventional_priorities`,
  `pct_priorities`, `pct_wipo_filed_only` continue to be copied from the
  parent exactly as in the original spec.

## Data model (patsync)

New nullable columns on `patent_project`:

| Column | Type | Notes |
|---|---|---|
| `parent_project_id` | INTEGER, FK → `patent_project.id` | Nullable. Set when a parent was picked. No cascade behavior needed — it's a soft reference for future traceability ("divisional of X"), not enforced anywhere at runtime beyond storage. |
| `parent_application_no` | VARCHAR/TEXT | Nullable. Copy of parent's `in_application_no` at pick time. |
| `parent_application_date` | DATE | Nullable. Copy of parent's `in_application_date` at pick time. |

Added via the existing idempotent migration pattern in
`app/database.py::_run_patent_metadata_migrations` (both the `postgresql`
and sqlite branches, `IF NOT EXISTS`-guarded `ALTER TABLE` statements,
matching how `application_type`/`provisional_kind`/etc. were added). Also
add a matching `.sql` file under `backend/migrations/` for the repo's
existing documentation convention (not auto-executed, but kept for
consistency with prior migrations there).

`PatentProject` (SQLModel) gains the three fields. `PatentProjectCreate`,
`PatentProjectUpdate`, and `PatentProjectRead` schemas gain
`parent_project_id: Optional[int]`, `parent_application_no: Optional[str]`,
`parent_application_date: Optional[date]`.

## Validation changes

New constant in `app/patents/validators.py`:

```python
DIVISIONAL_APPLICATION_TYPES = frozenset({
    "Ordinary Divisional",
    "Convention divisional",
    "PCT National Phase Entry - Divisional",
})
```

### Backend (`service.py`)

For these 3 types, **skip entirely**:
- `_validate_in_number_date_year_match()` (IN application number's embedded
  year vs `in_application_date` year).
- `validate_create_project_filing_windows()` (the 12-month
  priority-window and 31-month PCT-window date-math checks, **and** the
  "at least one priority/PCT row required" checks bundled inside that same
  function — both are bypassed together since the function is skipped as a
  whole for these types).

Still enforced, unchanged, for all types including these 3:
- `in_application_no` / `in_application_date` required when
  `project_mode == "final"` (the child's own values).
- Applicant/inventor required-for-final checks
  (`_validate_final_mode_contacts`).
- Format validators: `parse_in_application_number`,
  `validate_pct_international_number`.

New check, only for these 3 types: when `project_mode == "final"`, both
`parent_application_no` and `parent_application_date` must be present —
"Parent application number and date are required for divisional Final
Docket." Not enforced for Draft mode (consistent with how the child's own
IN no/date are also draft-optional today).

### Frontend (`patent-in-application.ts`, `patents-create.component.ts`)

- `inApplicationDateCrossValidator()`: add an early return of `null` when
  `application_type` is one of the 3 divisional types — before the
  existing convention/PCT branching — so no date-window cross-checks run
  for these types at all.
- `validateInNumberYearMatchesDate()` (component-level year-match check):
  same early-return-null guard for the 3 divisional types.
- `validateRequiredPriorityRows()` (component-level "at least one
  priority/PCT row required"): same early-return-null guard for the 3
  divisional types.
- New: `Validators.required` added to `parent_application_no` /
  `parent_application_date` controls only when both conditions hold:
  `project_mode === 'final'` AND `application_type` is one of the 3
  divisional types. Wired the same way `syncProjectModeFields()` already
  toggles validators on `in_application_no`/`in_application_date` — add a
  sibling `syncDivisionalParentFieldState()` called from the same
  `project_mode` and `application_type` value-change subscriptions.

## Implementation notes

- The `applyPartiesAndPriorityData()` helper (already extracted in the
  prior iteration) is unchanged — it still handles
  applicants/inventors/conventional_priorities/pct_priorities.
- `fillFromDivisionalParent()` changes: stop patching
  `in_application_no`/`in_application_date` from the parent row; instead
  patch `parent_application_no` / `parent_application_date` (disabled
  controls — `patchValue` still works on disabled controls) from the
  parent's `in_application_no` / `in_application_date`.
- `parent_project_id` is sent in the create/update payload as a plain
  numeric field set alongside the other copied data when a parent was
  picked; cleared (`null`) if the application type is changed away from a
  divisional type before submit.

## Error handling

Unchanged from the original spec (silent-empty-list on picker load
failure; `submitError` banner on detail-fetch failure — not applicable
anymore since no separate detail fetch exists, the list response already
carries full rows).

## Testing

- Backend: unit tests that for each of the 3 divisional types, a
  create/update payload with a year-mismatched IN number + IN date, or a
  priority date outside the 12/31-month window, or **no** priority rows at
  all, is accepted (no `ValueError`) — while the same payloads for
  non-divisional types (e.g. plain `Convention`, `PCT National Phase
  Entry`) still raise as before.
- Backend: a Final-mode create/update payload for a divisional type
  missing `parent_application_no`/`parent_application_date` is rejected.
- Backend: migration smoke test — new columns exist and are nullable on a
  fresh DB.
- Frontend: selecting a parent docket populates
  `parent_application_no`/`parent_application_date` as disabled/read-only,
  and leaves `in_application_no`/`in_application_date` untouched.
- Frontend: switching to a divisional type + Final mode makes
  `parent_application_no`/`parent_application_date` required; switching
  away clears that requirement.
- Frontend: date-mismatch / date-window / required-priority-row errors do
  not appear for the 3 divisional types but still appear for other types
  (regression check against existing tests).

## Out of scope

- No UI to browse "children of a given parent docket" (the FK is stored
  but not surfaced anywhere yet).
- No support for picking a Draft docket as parent (unchanged from
  original spec).
- No multi-select / merging data from more than one parent docket
  (unchanged).
