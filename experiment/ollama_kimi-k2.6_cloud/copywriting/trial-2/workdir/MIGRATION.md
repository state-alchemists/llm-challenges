# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. This guide walks through every breaking change and how to adapt your code.

---

## Breaking Changes

### 1. Base URL version prefix

All endpoints are now namespaced under `/v2/`.

**Before (v1):**
```http
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Update your HTTP client base URL or prepend `/v2` to every request path.

---

### 2. Authentication header changed

The custom `X-Auth-Token` header is replaced by a standard Bearer token. Requests sent with the old header will receive HTTP 401.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

Rename your auth configuration key if needed and update header construction.

---

### 3. Task `id` changed from integer to UUID

Task identifiers are now UUID strings instead of auto-incrementing integers. If your code assumes `id` is an integer, comparisons, URL formatting, or database schemas may break.

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

Change `id` fields in your models, databases, and path parameters from `int` to `string` (or UUID type).

---

### 4. Task field `done` renamed to `completed`

The boolean status field is now named `completed`. Using `done` in request bodies or expecting it in responses will fail or silently drop data.

**Before (v1):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

Search and replace `done` with `completed` in all JSON payloads and client models.

---

### 5. Task creation requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns HTTP 422.

**Before (v1):**
```json
{
  "title": "New task title"
}
```

**After (v2):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Ensure your application can resolve or prompt for a `project_id` before calling `POST /v2/tasks`. Existing tasks must be associated with a project during data migration.

---

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope containing `items`, `total`, and `next_cursor`. You must update deserialization and pagination logic.

**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Extract tasks from `response.items` instead of using the response body directly. To paginate, pass `?cursor=<next_cursor>` on subsequent requests.

---

## Migration Checklist

Use this checklist to ensure a complete upgrade.

1. **Update base URL**
   - [ ] Change API base URL to include `/v2/` prefix.

2. **Rotate authentication**
   - [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.

3. **Update data models**
   - [ ] Change task `id` type from `integer` to `string` (UUID).
   - [ ] Rename `done` field to `completed` in request/response models.
   - [ ] Add required `project_id` field to task creation payloads.

4. **Refactor list consumers**
   - [ ] Deserialize list responses from paginated envelope (`items`, `total`, `next_cursor`).
   - [ ] Implement cursor-based pagination instead of array pagination.

5. **Migrate existing data**
   - [ ] Map legacy integer IDs to new UUIDs.
   - [ ] Assign every existing task to a project.

6. **Validate integration**
   - [ ] Run test suite against v2 endpoints.
   - [ ] Verify task CRUD, listing, and pagination in staging.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
zrb self-update v2
```

After upgrading, run `zrb --version` to confirm you are on v2, then begin the checklist above.
