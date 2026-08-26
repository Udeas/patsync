# Divisional Parent-Docket Autofill

## Problem

When creating a new Docket whose Application Type is a divisional type
(`Ordinary Divisional`, `Convention divisional`, `PCT National Phase Entry -
Divisional`), the user currently has to re-type application no/date, title,
applicants, inventors, and priority data that already exists on the parent
docket. This is error-prone and slow.

## Scope

Frontend only (`frontend` repo). No backend changes, no DB migration, no
persisted parent-child link. Pure client-side autofill convenience at
create time.

## Trigger

- Only in **create mode** of `PatentsCreateComponent` (not edit mode).
- Only when `application_type`'s value contains `"Divisional"`
  (case-insensitive substring match), covering all three current divisional
  options without hardcoding each one.
- Independent of Docket Type (`project_mode`) — applies to both Draft and
  Final.

## UI

- New field block inserted in `patents-create.component.html`, positioned
  after the Attorney/Client selects and their selected-card summary, and
  before the `APPLICATION TITLE` label.
- Rendered only when the trigger condition (above) is true.
- Native `<input list="divisional-parent-options">` + `<datalist>`
  typeahead — no new UI library, consistent with the rest of the form's
  plain HTML elements.
- Each `<option>` label: `"{client_code} - {docket_no}"`.
- Field label: `"Copy details from existing Docket"`, with the input
  itself optional (skippable — user can ignore and fill manually).

## Data source

- Lazy-loaded: the list of candidate parent dockets is fetched once, the
  first time the trigger condition becomes true (not on component init),
  and cached in a signal for the rest of the session.
- Call `GET /api/patents/projects?include_archived=false` (existing
  endpoint, no backend change).
- Filter client-side to `project_mode === 'final'` — only Final Dockets
  are offered as parents, since Draft dockets may lack application
  no/date/priority data worth copying.

## On select

When the user picks an option matching a known `client_code - docket_no`
pair:

1. Resolve the matching project's `id` from the cached list.
2. Fetch full detail via existing `GET /api/patents/projects/{id}`.
3. Apply the following fields onto the current form, **overwriting**
   whatever is currently in them:
   - `application_title`
   - `in_application_no`, `in_application_date`
   - `applicants` (replace the FormArray rows)
   - `inventors` (replace the FormArray rows)
   - `conventional_priorities` (replace the FormArray rows)
   - `pct_priorities` (replace the FormArray rows)
   - `pct_wipo_filed_only`
4. Fields intentionally **not** touched: `docket_no`, `client_docket_no`,
   `application_type`, `project_mode`, `attorney_id`, `client_id` — these
   belong to the new docket being created and were already set by the
   user before reaching this step.
5. After applying, re-run existing sync methods
   (`syncPrioritySectionState`, `syncInNumberYearMismatchError`,
   `bindPriorityDateRecheck`) so validation/derived state stays correct,
   same as `prefillFromProject` already does today.
6. All copied fields remain plain form values — fully editable by the
   user afterward. No read-only lock, no visual "copied" marker beyond
   the normal filled-in inputs.

If the user changes the datalist input again to a different valid option,
re-apply the same overwrite (last selection wins). If the input is cleared
or doesn't match any known option, nothing is applied/changed.

## Implementation notes

- Refactor the row → FormArray-population logic currently inline in
  `PatentsCreateComponent.prefillFromProject` (docket-detail load for edit
  mode) into a shared private helper, e.g.:

  ```ts
  private applyPartiesAndPriorityData(row: ProjectDetailRow): void
  ```

  containing the applicants/inventors/conventional_priorities/pct_priorities
  FormArray-rebuild logic (currently duplicated shape between edit-mode
  load and this new feature).

  - `prefillFromProject` (edit mode) calls this helper *and* additionally
    patches docket-identity fields (`docket_no`, `application_type`,
    `project_mode`, `attorney_id`, `client_id`, `client_docket_no`).
  - The new divisional-autofill path calls the same helper plus patches
    only `application_title`, `in_application_no`, `in_application_date`,
    `pct_wipo_filed_only` — it must NOT patch docket-identity fields.

- New signals/state needed on `PatentsCreateComponent`:
  - `divisionalParentOptions = signal<PatentProjectSummary[]>([])` (or
    reuse a lighter list type — just need `id`, `docket_no`,
    `client.client_code`) — populated lazily.
  - A flag/signal to avoid re-fetching the list on every keystroke/type
    change once already loaded.
  - `showDivisionalParentPicker = computed(...)` mirroring the existing
    `showConventionalPrioritySection` / `showPctPrioritySection` pattern,
    based on `applicationTypeValue()`.

- No new backend endpoint. No new schema fields. No migration.

## Error handling

- If the lazy list fetch fails, fail silently to an empty list (consistent
  with existing `loadDropdowns()` pattern for clients/agents) — the picker
  becomes a no-op datalist with no options; user can still fill the form
  manually.
- If the detail fetch (`GET /projects/{id}`) fails after a selection, show
  the existing `submitError` banner pattern with a message like "Unable to
  load selected docket's details." and leave the form unchanged.

## Testing

- Unit test: selecting a divisional `application_type` reveals the picker;
  selecting a non-divisional type hides it.
- Unit test: applying a fetched row populates the expected fields and
  leaves docket-identity fields untouched.
- Unit test: switching selection twice re-applies (overwrites) from the
  second pick.
- Existing edit-mode (`prefillFromProject`) tests continue to pass
  unchanged after the refactor extracts the shared helper.

## Out of scope

- No persisted `parent_project_id` link or traceability.
- No support for picking a Draft docket as parent.
- No multi-select / merging data from more than one parent docket.
