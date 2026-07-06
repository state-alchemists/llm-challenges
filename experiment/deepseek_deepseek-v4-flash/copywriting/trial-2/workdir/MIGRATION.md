# Migrating from Zrb API v1 to v2

Zrb v2 introduces projects, pagination, stricter authentication, and several
field-level changes. This guide covers every breaking change between v1 and v2
with before/after examples. Read it top to bottom, then follow the checklist
at the end.

---

## Breaking Changes at a Glance

| Area | v1 | v2 |
|------|----|----|
| Endpoint prefix | `/tasks` | `/v2/tasks` |
| Authentication | `X-Auth-Token` header | `Authorization: Bearer` header |
| Task ID type | Integer | UUID string |
| Task completion field | `done` | `completed` |
| Task creation | `title` only | `title` + `project_id` (required) |
| List response | Bare array | Paginated envelope |
| Pagination | None | Cursor-based (`cursor`, `limit`) |

---

## 1. Endpoint Path Prefix

All resource paths now live under `/v2/`.

**Before (v1):**

```
GET /tasks
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

Requests to v1 paths will receive HTTP 404 or be routed to a legacy handler
(depending on deployment). Update your client's base URL or path prefix.

---

## 2. Authentication

The auth mechanism has changed from a custom header to the standard Bearer
token scheme.

**Before (v1):**

```
X-Auth-Token: <your_api_key>
```

**After (v2):**

```
Authorization: Bearer <your_api_token>
```

Requests using `X-Auth-Token` will receive HTTP 401. Migrate all credential
storage and request-building code. If your v1 key differs from your v2 token,
obtain a fresh token from the dashboard.

---

## 3. Task ID Type

Task IDs are now UUID strings instead of auto-incrementing integers. This
affects every endpoint that references a task by ID.

**Before (v1):**

```json
{"id": 42, "title": "Write tests", "done": false}
```

**After (v2):**

```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false}
```

Update:
- **URL construction:** `GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- **Local storage and cache schemas** — the ID field is now a string
- **Any code that assumes sequential integer IDs** (e.g., range queries, ID
  sorting, "next ID" prediction) — those patterns are no longer valid
- **Foreign-key references in your own data** that store task IDs

---

## 4. Field Rename: `done` → `completed`

The boolean field indicating task completion has been renamed.

**Before (v1) — response body:**

```json
{"id": 1, "title": "Ship v1", "done": true}
```

**After (v2) — response body:**

```json
{"id": "a1b2c3d4-...", "title": "Ship v1", "completed": true}
```

**Before (v1) — update request:**

```json
{"done": true}
```

**After (v2) — update request:**

```json
{"completed": true}
```

Search your codebase for all reads and writes of `done` on task objects and
rename them to `completed`. The v2 API ignores the `done` field — it does
not error, but it also does not update the task state.

---

## 5. New Required Field: `project_id`

Task creation now requires a `project_id` string. This is a hard requirement.

**Before (v1):**

```json
POST /tasks
{"title": "New task title"}
```

**After (v2):**

```json
POST /v2/tasks
{"title": "New task title", "project_id": "proj_abc123"}
```

Omitting `project_id` returns HTTP 422 with a validation error. You will need
a project to exist before creating tasks — obtain a `project_id` via
`GET /v2/projects` (new in v2) or from your dashboard.

---

## 6. List Response Format (Pagination)

List endpoints no longer return a bare array. They return a paginated envelope
with metadata and cursor-based pagination.

**Before (v1) — `GET /tasks`:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**After (v2) — `GET /v2/tasks`:**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false},
    {"id": "e5f6a7b8-...", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Update all list-consuming code to:
- Read from `.items` instead of treating the response as the array directly
- Optionally handle pagination via `?cursor=<next_cursor>` and `?limit=<n>`
  (default limit is 20)
- Stop when `next_cursor` is absent or `null` (no more pages)

**Example client-side pagination loop (pseudocode):**

```python
cursor = None
while True:
    params = {"limit": 100}
    if cursor:
        params["cursor"] = cursor
    resp = client.get("/v2/tasks", params=params)
    data = resp.json()
    for task in data["items"]:
        process(task)
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

---

## Step-by-Step Migration Checklist

- [ ] **Update endpoint paths.** Replace `/tasks` with `/v2/tasks` in all
      URL templates and client configuration.
- [ ] **Switch authentication.** Replace `X-Auth-Token` headers with
      `Authorization: Bearer` and obtain a v2 token if needed.
- [ ] **Migrate task ID storage.** Change any database columns, cache keys,
      or in-memory data structures that store task IDs from integer to
      UUID string.
- [ ] **Rename `done` to `completed`.** Update all response parsers, type
      definitions, and mutation request bodies.
- [ ] **Add `project_id` to task creation.** Identify where tasks are
      created, add the required `project_id` field, and populate it from
      your project listing or config.
- [ ] **Update list-response parsing.** Replace direct array access with
      `.items` on the response envelope. Add pagination loop logic if you
      fetch more than one page.
- [ ] **Run integration tests.** Point a subset of your test suite at v2
      and verify every endpoint + field maps correctly.

---

## Upgrade

```
pip install --upgrade zrb
```

Or, if you are using the API directly (not the CLI), update your client base
URL and credentials as described above. No SDK version bump is required for
plain HTTP clients — the migration is entirely in request/response format.
