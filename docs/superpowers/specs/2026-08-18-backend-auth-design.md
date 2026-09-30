# Backend Auth Integration — Design

Date: 2026-08-18
Status: Approved

## Problem

User login is UI-only. `frontend/src/app/auth/auth.service.ts` is a mock: users and
sessions live in `localStorage`, passwords are stored in plaintext, and all checks run
client-side (default `admin` / `admin123`). The backend has no user table and no auth;
every `/api/*` route is open. Anyone who reaches the API bypasses the login screen entirely.

## Goal

Replace the mock with real backend authentication:

1. Real users persisted in Postgres with hashed passwords.
2. JWT bearer login issued by the backend.
3. Existing `/api/*` data routes require a valid token.
4. No public signup — one seeded admin; further users created only by an authed admin.

Out of scope: Postgres Row Level Security (tracked separately), refresh tokens,
password reset / email flows, OAuth.

## Decisions

- **Mechanism:** JWT bearer token (HS256). Stateless, matches the existing
  `HttpClient` + `@env` frontend pattern.
- **Token lifetime:** 8 hours, no refresh token. Re-login on expiry.
- **Signup:** Seeded admin, no public signup. New users created via an admin-only
  endpoint (or DB). The frontend signup page is removed.
- **Hashing:** bcrypt via `passlib`.
- **JWT lib:** `python-jose[cryptography]`.

## Data Model

New `users` table. Added as a SQLModel model AND to `app/database.py`
`run_schema_migrations` (both the Postgres and SQLite branches, matching the existing
migration style — `CREATE TABLE IF NOT EXISTS`, idempotent).

| column         | type                    | notes                                   |
|----------------|-------------------------|-----------------------------------------|
| id             | serial / autoincrement  | primary key                             |
| username       | varchar, unique, not null | login id; matched case-insensitively  |
| display_name   | varchar                 |                                         |
| password_hash  | varchar, not null       | bcrypt                                  |
| role           | varchar, not null, default `user` | `admin` \| `user`; gates user creation |
| is_active      | bool, not null, default true |                                    |
| created_at     | timestamptz / text      | default now                             |
| updated_at     | timestamptz / text      | default now                             |

Unique index on `lower(username)` (Postgres) / unique `username` (SQLite).

## Backend Module — `app/auth/`

Mirrors the existing router/service split used elsewhere in the app.

- `models.py` — `User` SQLModel (`__tablename__ = "users"`).
- `schemas.py` — `LoginRequest`, `TokenResponse`, `UserCreate`, `UserOut`.
- `security.py` — `hash_password`, `verify_password` (bcrypt); `create_access_token`,
  `decode_access_token` (JWT). Reads `SECRET_KEY`, `ALGORITHM` (=`HS256`),
  `ACCESS_TOKEN_EXPIRE_MINUTES` (default 480) from settings/env.
- `deps.py` — `get_current_user` (extracts + validates Bearer token, loads active user);
  `require_admin` (depends on `get_current_user`, asserts `role == "admin"`).
- `service.py` — `authenticate(username, password)`, `create_user(...)`, `seed_admin()`.
- `router.py` — endpoints below.

### Settings

Extend `app/core/config.py` `Settings`:

- `SECRET_KEY: str` (required)
- `ACCESS_TOKEN_EXPIRE_MINUTES: int = 480`
- `AUTH_ADMIN_USERNAME: str | None = None`
- `AUTH_ADMIN_PASSWORD: str | None = None`

## Endpoints (`/api/auth`)

| method | path      | auth        | body / result                                   |
|--------|-----------|-------------|-------------------------------------------------|
| POST   | `/login`  | public      | `{username, password}` → `{access_token, token_type, user}` |
| GET    | `/me`     | bearer      | current `UserOut`                               |
| POST   | `/users`  | admin only  | `UserCreate` → `UserOut` (replaces public signup) |
| GET    | `/users`  | admin only  | `list[UserOut]`                                 |

Login failure and inactive users return `401`. Duplicate username on create returns `409`.
Non-admin hitting admin routes returns `403`.

## Protecting Existing Routes

In `app/main.py`, add `dependencies=[Depends(get_current_user)]` to the `include_router`
calls for the data routers:

- `applications_router`, `status_router`, `trademark_router`, `tm_status_router`,
  `patents_router`, `us_pto_router`

Left open: `health_router` and `GET /`. The new `auth_router` is included at
`/api/auth` (its own routes manage their own auth). One line changed per router; no
per-endpoint edits.

## Seed Admin

On startup, after `run_schema_migrations()`: if no user with `role = "admin"` exists,
create one from `AUTH_ADMIN_USERNAME` / `AUTH_ADMIN_PASSWORD`. If those are unset:
skip seeding in `DEBUG`, raise on startup otherwise (never fall back to a hardcoded
password).

## Frontend Changes

- Rewrite `auth.service.ts` to call the backend via `HttpClient` + `@env`:
  - `login(username, password)` → `POST /api/auth/login`; store `access_token` in
    localStorage; expose `isAuthenticated` / `userDisplayName` derived from the stored
    token (and/or a `/me` call).
  - `logout()` clears the stored token.
  - Remove `MockUser`, default credentials, `signup()`, and the users store.
- Remove the signup page (`signup.component.html` + its route) and the `guestGuard`
  entry that points to it. `authGuard` / `guestGuard` keep their current shape (still
  read `isAuthenticated`).
- Add `authInterceptor` (`HttpInterceptorFn`): attach `Authorization: Bearer <token>`
  to outgoing `/api` requests; on `401`, clear token + redirect to `/login`. Register
  in `app.config.ts` via `withInterceptors`.
- `login.component.ts` — `login()` becomes async (handles the HTTP result / error
  instead of a sync boolean).

## Error Handling

- Backend: invalid credentials / inactive → `401`; missing or bad token → `401`;
  non-admin on admin route → `403`; duplicate username → `409`. Consistent JSON
  `{"detail": ...}` (FastAPI default).
- Frontend: interceptor centralizes `401` → logout + `/login`. Login form surfaces the
  `401` as "Invalid username or password."

## Testing

Backend (pytest, existing `backend/tests/` style):

- `security`: hash → verify round-trip; wrong password fails; token encode → decode
  round-trip; expired/garbage token rejected.
- `login`: success returns token; bad password → 401; inactive user → 401.
- `deps`: protected route returns 401 without token, 200 with valid token.
- `admin gate`: non-admin `POST /users` → 403; admin → 201/200.

Frontend (existing `.spec.ts` style):

- `auth.service`: login stores token + flips `isAuthenticated`; logout clears it.
- `authInterceptor`: adds header; `401` triggers logout + redirect.

## Dependencies

Backend (`pyproject.toml`): `passlib[bcrypt]`, `python-jose[cryptography]`.

## Migration / Rollout Notes

- `users` migration is idempotent and additive; safe on the existing DB.
- Set `SECRET_KEY`, `AUTH_ADMIN_USERNAME`, `AUTH_ADMIN_PASSWORD` in backend `.env`
  before deploy. Document in `.env.example`.
- After deploy, existing frontend sessions (mock localStorage) are invalid; users log
  in again against the real backend.
