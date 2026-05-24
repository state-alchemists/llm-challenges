# Zrb Task API v1 → v2 Migration Guide

Zrb API v2 is a breaking release. It introduces projects, cursor-based pagination, stricter authentication, and renames several fields. This guide covers every change, with before/after examples, and ends with a checklist to track your migration.

---

## Overview of Breaking Changes

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoint prefix `/tasks` → `/v2/tasks` | All URLs change |
| 2 | Auth header `X-Auth-Token` → `Authorization: Bearer` | All requests rejected with HTTP 401 until updated |
| 3 | Task `id` integer → UUID string | ID-dependent code breaks; stored references incompatible |
| 4 | Field `done` → `completed` | Reads and writes of the old field silently ignored |
| 5 | `project_id` required on create | `POST /v2/tasks` returns HTTP 422 without it |
| 6 | List responses: bare array → paginated envelope | Response parsing breaks everywhere |

---

## Breaking Change 1: Endpoint Prefix

All endpoints move under `/v2/`.

**Before (v1):**

```
GET /tasks
POST /tasks
GET /tasks/42
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

**Action:** Update all URL path strings in your API client configuration.

---

## Breaking Change 2: Authentication Header

The `X-Auth-Token` header is replaced by the standard `Authorization: Bearer` scheme.

**Before (v1):**

```http
X-Auth-Token: sk_live_abc123
```

**After (v2):**

```http
Authorization: Bearer zrb_live_abc123
```

v2 rejects requests using `X-Auth-Token` with HTTP 401 and no body.

**Action:** Replace the header name and value format. Rotate tokens if your v1 keys were exposed to multiple services.

---

## Breaking Change 3: Task ID Type (Integer → UUID)

Task identifiers are now UUID strings instead of auto-incrementing integers. This affects every endpoint that references a task by ID, and any local state that caches task IDs.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

**Action:**
- Update client-side ID storage to strings, not integers.
- Replace any integer-based lookups (`tasksById[42]`) with UUID lookups.
- Note that old integer IDs are **not** reused or mapped — v2 tasks are a new namespace.
- Foreign-key references or local caches that used integer IDs must be rebuilt.

---

## Breaking Change 4: Field Rename (`done` → `completed`)

The `done` boolean field is renamed to `completed`. The old field is not included in v2 responses, and writing `done` in a request body has no effect.

**Before (v1) — response and update body:**

```json
{
  "done": false
}
```

**After (v2) — response and update body:**

```json
{
  "completed": false
}
```

**Action:**
- Rename all `done` references to `completed` in response deserialization.
- Change request bodies that set `done` to use `completed` instead.

---

## Breaking Change 5: `project_id` Required on Creation

v2 introduces projects. Every task must belong to exactly one project, so `project_id` is required when creating a task.

**Before (v1) — POST body (and resulting task):**

```json
// POST /tasks
{
  "title": "Write tests"
}
```

**After (v2) — POST body (and resulting task):**

```json
// POST /v2/tasks
{
  "title": "Write tests",
  "project_id": "proj_abc123"
}
```

Omitting `project_id` returns HTTP 422 with a validation error body.

**Action:**
- Create at least one project (refer to the v2 Projects API reference for the endpoint).
- Provide its `project_id` on every task creation call.
- Decide on a project strategy — one project per user, one per team, or a default project for legacy migrations.

---

## Breaking Change 6: Paginated Response Envelope

List endpoints no longer return a bare array. They return a paginated envelope with cursor-based navigation.

**Before (v1) — `GET /tasks`:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) — `GET /v2/tasks`:**

```json
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "c3d4...", "title": "Ship v2", "completed": true, "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

**Pagination usage:**

```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

The `next_cursor` field is `null` when there are no more pages.

**Action:**
- Extract the `items` key from the response envelope instead of consuming the top-level array.
- If your code paginates by page number, rewrite to use cursor-based navigation via the `next_cursor` value.
- Optional: pass `?limit=` to control page size (default 20).

---

## Non-Breaking Addition: Task Object Gains `project_id`

The task object now includes a `project_id` field when retrieved. This is a non-breaking addition for read paths — your existing deserialization should tolerate the extra field — but it becomes mandatory on creation (see Change 5).

---

## Migration Checklist

Use this checklist per service, in order. Each item links to the corresponding change above.

- [ ] **1. Endpoint prefix** — Replace `/tasks` with `/v2/tasks` in all API call sites.
- [ ] **2. Authentication** — Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] **3. Task IDs** — Change all task ID fields from `int` to `string`. Update local caches and foreign-key stores.
- [ ] **4. Field rename** — Rename `done` → `completed` in request bodies and response deserializers.
- [ ] **5. project_id** — Create projects via the v2 Projects API. Supply `project_id` on every `POST /v2/tasks`.
- [ ] **6. Pagination** — Unwrap list responses via `response.items`. Replace offset/page-number pagination with cursor logic using `next_cursor`.
- [ ] **7. Smoke test** — Run a single create → list → get → update → delete cycle against v2.
- [ ] **8. Integration tests** — Update test fixtures (v1 responses, cassettes, mocks) to match v2 shapes.

---

## Upgrade Command

Once your code is updated, point your client to the v2 base URL:

```bash
# Change this:
ZRB_API_URL=https://api.zrb.dev/v1

# To this:
ZRB_API_URL=https://api.zrb.dev/v2
```

The v1 API will remain available for a deprecation period (see deprecation schedule in the changelog). All new features and fixes target v2 only.
