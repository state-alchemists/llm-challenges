# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change between v1 and v2, with before/after examples for each.

---

## Breaking Changes

### 1. Endpoint Prefix: `/v2/`

All API endpoints are now prefixed with `/v2/`. Requests to `/tasks` return HTTP 404.

**Before (v1):**
```
GET /tasks
POST /tasks
GET /tasks/42
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication: `X-Auth-Token` → `Authorization: Bearer`

The authentication header has changed. The old `X-Auth-Token` header is rejected with HTTP 401.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Action:** Replace the header name and value in all clients. Generate a new Bearer token if your existing API key is not a v2 token.

---

### 3. Task ID: Integer → UUID String

The `id` field is now a UUID string instead of an auto-incrementing integer. All paths that reference a task by ID must use the new UUID format.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Action:** Change ID columns, variables, and URL templates from `int` to `string` (UUID). Lookups by ID must now pass a UUID string:

**v1 (curl):**
```bash
curl -H "X-Auth-Token: $KEY" https://api.zrb.dev/tasks/42
```

**v2 (curl):**
```bash
curl -H "Authorization: Bearer $TOKEN" https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Existing v1 integer IDs are **not** carried over — you must retrieve the new UUID mappings from the list endpoint.

---

### 4. Field Rename: `done` → `completed`

The boolean task field `done` has been renamed to `completed`. The v1 field name is not accepted in v2 requests.

**Before (v1):**
```json
{
  "title": "Write tests",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Write tests",
  "completed": true
}
```

**Action:** Update all read and write paths to use `completed`. This includes response parsing, request bodies, database mappings, and UI bindings.

---

### 5. New Required Field: `project_id`

Creating a task now requires a `project_id` string. Omitting it returns HTTP 422 Unprocessable Entity.

**Before (v1) — no project_id:**
```json
POST /tasks
{
  "title": "Buy milk"
}
```

**After (v2) — project_id required:**
```json
POST /v2/tasks
{
  "title": "Buy milk",
  "project_id": "proj_abc123"
}
```

**Action:** Allocate a default project for existing v1 tasks during migration, or ensure your creation flow collects a `project_id`. Use the projects endpoint to list available projects:

```
GET /v2/projects
```

---

### 6. List Responses: Bare Array → Paginated Envelope

The list tasks endpoint no longer returns a bare array. It returns a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1):**
```json
GET /tasks
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
```json
GET /v2/tasks
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "d5e6...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

**Action:** Update response parsing to unwrap `response.items` instead of reading the array directly. Use `next_cursor` for pagination:

```python
# v1 (breaks in v2)
tasks = response.json()
for task in tasks:
    print(task["title"])

# v2
data = response.json()
tasks = data["items"]
for task in tasks:
    print(task["title"])
# Paginate
cursor = data.get("next_cursor")
```

---

## Migration Checklist

Use this checklist to track your progress.

- [ ] **Update endpoint URLs** — Add `/v2/` prefix to all API paths.
- [ ] **Update auth header** — Replace `X-Auth-Token` with `Authorization: Bearer` and generate a valid Bearer token.
- [ ] **Migrate task IDs** — Change all ID fields, variables, and route templates from integer to UUID string.
- [ ] **Rename `done` to `completed`** — Update request bodies, response parsing, database schemas, and UI code.
- [ ] **Add `project_id` to task creation** — Ensure every `POST /v2/tasks` call includes a valid `project_id`.
- [ ] **Update list response parsing** — Unwrap `response["items"]` from the new paginated envelope instead of reading the array directly.
- [ ] **Adopt cursor-based pagination** — Replace offset/limit logic with the `?cursor=` parameter and `next_cursor` value from responses.
- [ ] **Run integration tests** — Verify every endpoint works end-to-end against the v2 API.
- [ ] **Deprecate v1 tokens** — Revoke old `X-Auth-Token` keys after all clients are migrated.

---

## Upgrade

Install the latest v2 release:

```bash
pip install zrb-cli --upgrade
```
