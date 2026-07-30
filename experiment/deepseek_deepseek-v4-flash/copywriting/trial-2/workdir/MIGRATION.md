# Zrb CLI v1 → v2 Migration Guide

**Target audience:** experienced developers currently using Zrb v1.

v2 introduces projects as a first-class concept, cursor-based pagination for list endpoints, stronger authentication conventions, and several breaking changes to the task API. This guide covers every change you need to make to port your code.

---

## Table of Contents

1. [Endpoint Prefix](#1-endpoint-prefix)
2. [Authentication Header](#2-authentication-header)
3. [Task ID Type: Integer → UUID](#3-task-id-type-integer--uuid)
4. [Field Rename: `done` → `completed`](#4-field-rename-done--completed)
5. [New Required Field: `project_id`](#5-new-required-field-project_id)
6. [List Response: Bare Array → Paginated Envelope](#6-list-response-bare-array--paginated-envelope)
7. [Migration Checklist](#migration-checklist)
8. [Upgrade Command](#upgrade-command)

---

## 1. Endpoint Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1):**

```
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

Update your base URL configuration or every hardcoded path. Requests to the old `/tasks` paths will receive a `404` (or `301` if you configure a redirect — but rely on the direct `/v2/` path).

---

## 2. Authentication Header

The header name and value format have both changed.

**Before (v1):**

```
X-Auth-Token: sk-abc123...
```

**After (v2):**

```
Authorization: Bearer sk-abc123...
```

v2 returns `HTTP 401` for requests using `X-Auth-Token`. Update your client's auth middleware or request builder.

---

## 3. Task ID Type: Integer → UUID

Task IDs are now UUID v4 strings. Any code that assumes an integer type — comparison, serialisation, or storage — must be updated.

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

### What to check

- **URL construction:** `GET /tasks/42` → `GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- **Client-side caches / maps:** change key types from `int` to `string`.
- **Local state:** sequence counters, integer auto-increment, or integer-only DB columns will not match server IDs.
- **Comparisons:** `task.id == 42` → `task.id == "a1b2c3d4-..."`.
- **Logging / display:** integer formatting may need updating for string output.

v1 integer IDs are **not reused** as UUIDs. There is no deterministic mapping. If you have stored v1 IDs, you will need to reconcile them with the new UUIDs the server returns.

---

## 4. Field Rename: `done` → `completed`

The boolean field that tracks task completion has been renamed.

**Before (v1) — creating or updating a task:**

```json
{
  "title": "Ship v2",
  "done": false
}
```

**After (v2):**

```json
{
  "title": "Ship v2",
  "completed": false
}
```

### What to check

- `POST /v2/tasks` — send `completed`, not `done`.
- `PUT /v2/tasks/{id}` — send `completed`, not `done` (the server **ignores** `done`; it does not map it).
- All reads now return `completed`. Update any client code that references `response.done` or `task["done"]`.

---

## 5. New Required Field: `project_id`

Every task now belongs to a project. The `project_id` field is **required** on creation.

**Before (v1) — create task:**

```http
POST /tasks

{
  "title": "Write tests"
}
```

**After (v2):**

```http
POST /v2/tasks

{
  "title": "Write tests",
  "project_id": "proj_abc123"
}
```

Omitting `project_id` now returns `HTTP 422 Unprocessable Entity`.

### Migration steps

1. Decide how you map existing v1 tasks to projects (e.g., one catch-all project, or one per team/workspace).
2. Obtain a valid `project_id` via the new projects API (see [Zrb Projects Reference](https://docs.zrb.sh/projects) — not covered in this guide).
3. Update every `POST /v2/tasks` call to include `project_id`.
4. Update any bulk-import or seed scripts.

The `project_id` is read-only after creation. To move a task to another project, delete and re-create it.

---

## 6. List Response: Bare Array → Paginated Envelope

v1 returned a plain JSON array for list endpoints. v2 returns a paginated envelope object with cursor-based navigation.

**Before (v1) — list tasks response:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "2024-01-10T09:00:00Z"},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "2024-01-11T14:30:00Z"}
]
```

**After (v2):**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-10T09:00:00Z"},
    {"id": "e5f6a7b8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "2024-01-11T14:30:00Z"}
  ],
  "total": 2,
  "next_cursor": null
}
```

### What to check

- **Access items via `response.items`**, not `response[0]`.
- **Pagination is now cursor-based**, not page-number-based. Pass `?cursor=<next_cursor>` (returned in the response) to fetch the next page. Use `?limit=<N>` to control page size (default 20).
- **`total`** gives the total number of matching items across all pages.
- When `next_cursor` is `null`, there are no more pages.

**Before (v1) — iterating over all tasks (pseudo-code):**

```python
for task in client.get("/tasks"):
    process(task)
```

**After (v2):**

```python
cursor = None
while True:
    resp = client.get("/v2/tasks", params={"cursor": cursor})
    for task in resp["items"]:
        process(task)
    cursor = resp.get("next_cursor")
    if cursor is None:
        break
```

---

## Migration Checklist

Complete these steps in order:

- [ ] **Update auth header.** Replace `X-Auth-Token` with `Authorization: Bearer` everywhere.
- [ ] **Repoint all endpoint URLs.** Prefix every API path with `/v2/`.
- [ ] **Handle UUID IDs.** Update client code that stores, compares, or formats task IDs — no more `int`.
- [ ] **Rename `done` → `completed`.** Update request payloads (`POST`, `PUT`) and response readers.
- [ ] **Add `project_id` to task creation.** Decide on a project structure and include `project_id` in every `POST /v2/tasks`.
- [ ] **Update list-response parsers.** Read `response.items`, handle cursor-based pagination, and use `?limit=` instead of any page-number parameter.
- [ ] **Reconcile stored v1 IDs.** If you cache or reference v1 integer IDs locally, map them to the new UUIDs returned by the server.
- [ ] **Test.** Run through the full CRUD cycle: create, list, get, update, delete. Verify auth errors return `401` and missing `project_id` returns `422`.
- [ ] **Update documentation / API configs.** SDKs, client wrappers, Postman collections, OpenAPI specs, internal runbooks.

---

## Upgrade Command

```bash
zrb self upgrade --version v2-latest
```

After upgrading, regenerate your API token and update all environment variables and secrets:

```bash
zrb token rotate
```

Your old `X-Auth-Token` will be revoked. Update any `.env`, CI/CD secrets, or deployment configs with the new Bearer token.
