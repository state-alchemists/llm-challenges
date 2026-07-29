# Zrb CLI — v1 to v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, stricter authentication, and several breaking changes to the Task API. This guide covers every change you need to make to migrate from v1 to v2.

---

## Breaking Changes at a Glance

| Area | v1 | v2 |
|---|---|---|
| Endpoint prefix | `/tasks` | `/v2/tasks` |
| Authentication | `X-Auth-Token` header | `Authorization: Bearer` header |
| Task `id` type | Integer | UUID string |
| Task `done` field | `"done": true` | `"completed": true` |
| Task creation | `title` only | `title` + `project_id` (required) |
| List response | Bare array | Paginated envelope (`items`, `total`, `next_cursor`) |
| List pagination | None | Cursor-based (`?cursor=`, `?limit=`) |

---

## 1. Endpoint Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1):**

```
GET  /tasks
GET  /tasks/{id}
POST /tasks
PUT  /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```
GET  /v2/tasks
GET  /v2/tasks/{id}
POST /v2/tasks
PUT  /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

> Requests to `/tasks` (without the `/v2/` prefix) will return HTTP 404 or route to a deprecated v1 handler — update every endpoint URL in your client code.

---

## 2. Authentication Header

The `X-Auth-Token` header is replaced by the standard `Authorization: Bearer` scheme. Requests using the old header receive HTTP 401.

**Before (v1):**

```
X-Auth-Token: abc123
```

**After (v2):**

```
Authorization: Bearer abc123
```

You'll also need a new API token from the Zrb dashboard — existing v1 API keys **will not work** with the Bearer scheme.

---

## 3. Task ID Type: Integer → UUID String

Task `id` values are now UUID strings instead of auto-incrementing integers.

**Before (v1):**

```json
{"id": 42, "title": "Write tests", "done": false}
```

**After (v2):**

```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false}
```

**Actions required:**

- Update any code that assumes `id` is an integer (type checks, arithmetic, integer serialization).
- Update any stored references to task IDs (local caches, URL construction, foreign keys in your database).
- `GET /v2/tasks/{id}` now expects a UUID string — passing an integer will fail.
- Each v2 task you create gets a new UUID; there is no migration path for old integer IDs. You will need to map existing v1 task IDs to their v2 equivalents if your application crosses this boundary.

---

## 4. Task Field Renamed: `done` → `completed`

The `done` field is renamed to `completed` in both request and response payloads. The semantics are unchanged — `false` means not done, `true` means done.

**Before (v1) — response:**

```json
{"id": 42, "title": "Write tests", "done": true}
```

**Before (v1) — update request:**

```json
{"done": true}
```

**After (v2) — response:**

```json
{"id": "a1b2c3d4-...", "title": "Write tests", "completed": true}
```

**After (v2) — update request:**

```json
{"completed": true}
```

**Actions required:**

- Rename all references from `done` to `completed` in your client-side data models and serialization code.
- Update any UI bindings, conditional logic, or derived state that reads or writes the `done` property.
- The old field name `done` is silently ignored in v2 — sending `{"done": true}` will not mark the task as completed.

---

## 5. Creating Tasks Now Requires `project_id`

Task creation in v1 only required a `title`. In v2, `project_id` is mandatory.

**Before (v1) — create request:**

```json
{
  "title": "Write tests"
}
```

**After (v2) — create request:**

```json
{
  "title": "Write tests",
  "project_id": "proj_abc123"
}
```

**Actions required:**

- Create or identify a project before creating tasks (see the Projects API — `GET /v2/projects` to list existing projects).
- Update all task creation code paths to include `project_id`.
- Omitting `project_id` returns HTTP 422 with a descriptive error body.

---

## 6. List Response Format: Bare Array → Paginated Envelope

v1 returned a bare JSON array. v2 wraps the result in a paginated envelope.

**Before (v1) — response:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**After (v2) — response:**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false},
    {"id": "e5f6g7h8-...", "title": "Ship v1", "completed": true}
  ],
  "total": 2,
  "next_cursor": null
}
```

**Actions required:**

- Access the task list via `response.items` instead of the response itself.
- Use `response.next_cursor` to detect more pages — pass it as `?cursor=<value>` to fetch the next page.
- Use `response.total` for UI counters or summary displays instead of `response.length`.

---

## 7. List Pagination: Cursor-Based

v1 returned all results (no pagination). v2 uses cursor-based pagination with configurable page size and no implied ordering across pages.

**Before (v1):**

```
GET /tasks
```

**After (v2):**

```
GET /v2/tasks?limit=20
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

- `limit` — max results per page (default 20, maximum 100).
- `cursor` — opaque cursor returned as `next_cursor` in the previous page's envelope.
- When `next_cursor` is `null`, you've reached the last page.

---

## Step-by-Step Migration Checklist

- [ ] **Regenerate API tokens.** Generate Bearer tokens from the Zrb dashboard. Old `X-Auth-Token` keys are invalid.
- [ ] **Update all endpoint URLs.** Replace `/tasks` with `/v2/tasks` in every API call.
- [ ] **Update the auth header.** Replace `X-Auth-Token: <key>` with `Authorization: Bearer <token>`.
- [ ] **Update task data models.** Change `id` type from integer to string (UUID), rename `done` to `completed`, add `project_id`.
- [ ] **Update create-task calls.** Add `project_id` to the request body.
- [ ] **Update list-response parsing.** Read `response.items` instead of the bare array. Handle `next_cursor` for pagination.
- [ ] **Add pagination logic.** Implement cursor-based page iteration via the `?cursor=` parameter.
- [ ] **Update stored task IDs.** If your application caches or references task IDs, convert them to the new UUID format.
- [ ] **Update CI/CD or scripts.** Any automation scripts, seed data, or test fixtures that use the v1 format must be updated.
- [ ] **Test against the v2 staging environment.** Run through all CRUD operations before pointing production traffic to v2.

---

## Upgrade Command

```bash
# Install or upgrade to Zrb CLI v2
pip install --upgrade zrb

# Verify the installed version
zrb --version
# Should output: zrb 2.x.x
```

If you're using an API client library, update that as well:

```bash
# Python
pip install --upgrade zrb-client

# JavaScript / Node
npm install @zrb/client@latest
```
