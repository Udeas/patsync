# Audit Log — Design Spec

**Date:** 2026-08-19
**Status:** Approved (brainstorming), pending implementation plan
**Repos:** `patsync` (backend, branch `main`), `frontend` (Angular, branch `feat/deadlines-page`)

## Goal

Give an admin a trail of what changed in the system: who did it, when, what action, which entity, and which fields changed. Covers data create/update/delete, status changes, and auth events. Viewable through an admin-only page backed by an admin-only API.

## Scope

**Captured events**
- Data mutations (create / update / delete) on the core entities: patents, design applications, trademark applications, clients, agents.
- Status changes (patent / design / trademark), including the new patent abandon reason.
- Auth events: successful login, failed login, user create, user deactivate.

**Not captured (v1 non-goals)**
- Reads / views.
- Per-child-field diffs for nested collections (a patent's applicants / inventors / priorities). A parent edit that only touches children is recorded as a parent `update` row with an empty (or coarse) `changes` array.
- Log export, retention / rotation, tamper-proofing.

## Access Control

All audit surfaces are admin-only.

- New dependency `get_current_admin` (in `app/auth/deps.py`) wraps `get_current_user` and raises `HTTPException(403, "Admin access required")` when `user.role != "admin"`.
- The audit API router mounts with `dependencies=[Depends(get_current_admin)]`.
- The frontend audit route + its nav link are shown only when the logged-in user's `role === 'admin'`; the route also has a guard that redirects non-admins.

## Data Model

New table `audit_log`. New SQLModel `AuditLog` in `app/auth/models.py` (co-located with `User`, since auditing is an auth/admin concern).

| column | type | notes |
|--------|------|-------|
| `id` | int PK | |
| `created_at` | datetime (tz) | default now, indexed |
| `actor_user_id` | int, nullable | FK-ish to `users.id`; null for failed login |
| `actor_username` | str, nullable | denormalized for display even if user later deleted |
| `action` | str | one of: `create`, `update`, `delete`, `status_change`, `login`, `login_failed`, `user_create`, `user_deactivate` |
| `entity_type` | str, nullable | one of: `patent`, `design`, `trademark`, `client`, `agent`, `user`; null for login events |
| `entity_id` | int, nullable | pk of affected row; null for auth-only events |
| `entity_label` | str, nullable | human label: docket_no / project_code / client name / username |
| `changes` | str (JSON), nullable | JSON array of `{ "field": str, "old": any, "new": any }`; empty/`[]` for create + auth events |
| `ip_address` | str, nullable | filled for auth events; best-effort from request |

Indexes: `created_at` (desc scans), `actor_user_id`, `entity_type`, `action`.

`changes` is stored as a JSON string (SQLite has no native JSON type here; Postgres uses TEXT for parity with existing columns). Values are coerced to JSON-safe primitives (dates → ISO strings).

### Migration

Add `audit_log` creation to `app/database.py`:
- Postgres branch: `CREATE TABLE IF NOT EXISTS audit_log (...)` + `CREATE INDEX IF NOT EXISTS` for the four indexes, following the existing idempotent pattern (mirroring `_run_users_migration`).
- SQLite branch: same via `CREATE TABLE IF NOT EXISTS` + indexes.
- Backend unit tests build the schema with `SQLModel.metadata.create_all`, so the model alone suffices in tests; the migration is for the real DB.

## Capture Mechanism

### A. ORM event listener (data create/update/delete)

New module `app/audit/__init__.py` + `app/audit/listener.py`:

- Register a SQLAlchemy `before_flush` listener on the `Session` (registered once at app startup, alongside engine setup). During flush it inspects `session.new`, `session.dirty`, `session.deleted`.
- **Allow-list of audited ORM models** → `entity_type` + label field:
  - `PatentProject` → `patent`, label `docket_no`
  - `ApplicationData` → `design`, label `project_code`
  - `TmApplicationData` → `trademark`, label `project_code`
  - `PatentClient` → `client`, label `name`
  - `PatentAgent` → `agent`, label `name`
  Any other model (child rows like `PatentApplicant`, `PatentStatusEvent`, `ApplicationState`, etc.) is ignored by the listener.
- For `dirty` (update): compute field diffs from SQLAlchemy attribute history (`inspect(obj).attrs[x].history`), skipping fields in the **ignore-list**: `created_date`, `modified_date`, `last_status_updated_at`. If no meaningful field changed, emit no row (avoids noise from touch-only updates). Note: a parent `update` whose only real change is in child collections yields no field diff → still emit a single `update` row with `changes = []` so the action is visible.
- For `new` (create): `action = create`, `changes = []`.
- For `deleted` (delete): `action = delete`, `changes = []`.
- Actor: read from a request-scoped `ContextVar` (see C). If unset (e.g. startup seeding), `actor_*` are null.
- The listener stages `AuditLog` rows into the same session so they commit atomically with the change. (Staged in `before_flush` via `session.add`; SQLAlchemy processes them in the same transaction.)

Values captured for `old`/`new` are JSON-coerced (dates → ISO, Decimal → str, everything else passed through if JSON-serializable, else `str()`).

### B. Explicit audit calls (status changes + auth)

Some events either don't map to a clean parent-row diff or occur outside the ORM allow-list:

- **Status changes** — one `record_status_change(...)` call added inside each status service function:
  - patents `update_status_event` (`app/patents/service.py`)
  - design `update_application_status` (`app/services/application_service.py`)
  - trademark `update_tm_application_status` (`app/services/trademark_service.py`)
  Logs `action = status_change`, `entity_type`/`id`/`label` of the parent, and `changes = [{field:"status", old:<old label>, new:<new label>}]`; for a patent Abandoned change it also appends `{field:"abandon_reason", old:null, new:<reason>}`.

  **De-dup rule (listener vs explicit):** `record_status_change` sets a per-request marker in the audit context recording `(entity_type, entity_id)` as "already audited this request". The `before_flush` listener, before emitting any row, checks that marker and skips `update` rows for a parent entity already covered by an explicit status_change in the same request. Status-event INSERTs (`PatentStatusEvent`, `ApplicationState`, `TmApplicationState`) are on non-audited child tables and ignored regardless. Net: a status change yields exactly one `status_change` row, never a duplicate generic `update`.
- **Auth events** — explicit calls in `app/auth/service.py` / `app/auth/router.py`:
  - `login` (success): actor = the user, `ip_address` from request.
  - `login_failed`: actor null, `actor_username` = attempted username, `ip_address` from request.
  - `user_create`: actor = admin, entity_type `user`, entity_id/label of the new user.
  - `user_deactivate`: actor = admin, entity `user`, `changes = [{field:"is_active", old:true, new:false}]`.

Explicit calls write via a small helper `write_audit(session, **fields)` in `app/audit/service.py`.

### C. Actor context

New `app/audit/context.py` with a `ContextVar[Optional[AuditActor]]` (`AuditActor` = small dataclass of `user_id`, `username`). Set it in the auth dependency `get_current_user` (after resolving the user) so every authenticated request has the actor available to the ORM listener; reset is handled per-request (contextvars are naturally request-scoped under the async/threaded worker; set on each `get_current_user` call). Auth events pass actor explicitly rather than relying on the context (login has no prior actor).

## API

New router `app/audit/router.py`, mounted in `app/main.py` at `/api/audit` with `dependencies=[Depends(get_current_admin)]`.

`GET /api/audit`
- Query params: `page` (default 1), `page_size` (default 25, max 100), `actor` (username substring), `entity_type`, `action`, `date_from` (ISO date), `date_to` (ISO date).
- Response: `{ items: AuditLogRead[], total: int, page: int, page_size: int }`, newest-first (`created_at desc, id desc`).
- `AuditLogRead` schema (in `app/audit/schemas.py`): `id, created_at, actor_username, action, entity_type, entity_id, entity_label, changes (parsed JSON array), ip_address`.

## Frontend

New standalone component `AuditLogComponent` under `src/app/admin/audit/`:
- Route `/admin/audit`, protected by an `adminGuard` (checks decoded role from the stored token / a `me` lookup; redirects non-admins to the dashboard).
- Nav link "Audit Log" added to the app shell / sidebar, rendered only when `role === 'admin'`.
- UI: filter bar (user text, entity-type select, action select, date-from, date-to) + paginated table (Time, User, Action, Entity, Label, Changes) reusing existing `ui-card` / table / pagination styles. The Changes cell renders the `{field, old→new}` list compactly (e.g. `status: Filed → Abandoned`).
- Calls `GET {apiBaseUrl}/api/audit` with the bearer token (existing interceptor) and the filter/page params.

Types added to a small `audit-types.ts` (`AuditLogRow`, `AuditListResponse`).

## Testing

**Backend (pytest, in-memory SQLite via `create_all`):**
- Listener: create → one `create` row with correct entity_type/label; update of a real field → `update` row with correct `changes` diff; update touching only ignore-listed fields → no row; delete → `delete` row; change on a non-audited model (e.g. `PatentApplicant`) → no row.
- Actor: with the context var set, rows carry actor_user_id/username; unset → nulls.
- Status change: each of the 3 status functions writes a `status_change` row with old→new label; patent Abandoned includes the abandon_reason change and does not also emit a redundant generic parent `update` row.
- Auth: login writes `login` (+ip); bad password writes `login_failed` with attempted username and null actor; user create/deactivate write their rows.
- API: `GET /api/audit` returns newest-first, paginates, and each filter narrows results; non-admin token → 403; unauthenticated → 401.

**Frontend (vitest):**
- Audit page renders rows from a mocked API response, applies filters (issues the right query params), paginates, and renders a changes cell as `field: old → new`.
- Admin guard: non-admin is redirected; admin is allowed.

## File Structure

**Backend (new unless noted)**
- `app/audit/__init__.py`
- `app/audit/context.py` — `AuditActor`, `current_actor` ContextVar, set/reset helpers.
- `app/audit/listener.py` — SQLAlchemy `before_flush` registration + diff logic + allow/ignore lists.
- `app/audit/service.py` — `write_audit(...)`, `record_status_change(...)`, JSON coercion helper.
- `app/audit/schemas.py` — `AuditLogRead`, list response.
- `app/audit/router.py` — `GET /api/audit`.
- `app/auth/models.py` (modify) — add `AuditLog` model.
- `app/auth/deps.py` (modify) — add `get_current_admin`; set actor context in `get_current_user`.
- `app/auth/service.py` / `app/auth/router.py` (modify) — auth-event audit calls.
- `app/patents/service.py`, `app/services/application_service.py`, `app/services/trademark_service.py` (modify) — status-change audit calls.
- `app/database.py` (modify) — `audit_log` migration (PG + SQLite).
- `app/main.py` (modify) — register listener at startup; mount audit router.
- `tests/test_audit_listener.py`, `tests/test_audit_status_and_auth.py`, `tests/test_audit_api.py` (new).

**Frontend (new unless noted)**
- `src/app/admin/audit/audit-log.component.ts` / `.html` / `.css`
- `src/app/admin/audit/audit-types.ts`
- `src/app/admin/audit/audit-log.component.spec.ts`
- admin route guard (new small `admin.guard.ts`) + route registration (modify routes)
- nav/shell (modify) — conditional "Audit Log" link.

## Open Risks / Notes

- The redundant-row suppression relies on the per-request "already audited" marker (see the De-dup rule in Capture §B). The marker lives in the audit context and is cleared per request; verify it doesn't leak across requests under the worker model.
- ContextVar propagation must hold across the request's DB work under the deployment's worker model (uvicorn default). If a future async path breaks propagation, actor may be null — acceptable degradation (row still written).
- Spans two repos and two branches; implementation plan should sequence backend first (API contract), then frontend against it.
