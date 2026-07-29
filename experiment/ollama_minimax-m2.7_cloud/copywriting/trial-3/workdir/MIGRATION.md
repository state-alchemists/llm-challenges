# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Each section shows the v1 approach, the v2 replacement, and what you need to do.

## Breaking Changes

### 1. Endpoint Prefix Changed

All endpoints are now versioned under `/v2/`.

**Before (v1):**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication Header Changed

The header format changed from a custom token header to a standard Bearer token.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

Requests using `X-Auth-Token` will receive `401 Unauthorized`. Update your HTTP client configuration to use the `Authorization` header with a `Bearer` prefix.

---

### 3. Task ID Type Changed: Integer → UUID

Task IDs are no longer integers. They are now UUID strings.

**Before (v1) — task id is an integer:**
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z"}
```

**After (v2) — task id is a UUID string:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
```

Update any code that parses or stores task IDs to handle UUID strings instead of integers. Database columns storing task IDs should be migrated from `INTEGER` to `VARCHAR(36)` or equivalent.

---

### 4. Task Field Renamed: `done` → `completed`

The `done` boolean field is renamed to `completed`.

**Before (v1):**
```json
{"title": "Updated title", "done": true}
```

**After (v2):**
```json
{"title": "Updated title", "completed": true}
```

This affects both request bodies (Update Task) and response bodies. Search your codebase for `.done` and `done:` references and rename them to `.completed` and `completed:`.

---

### 5. Task Creation Now Requires `project_id`

Creating a task no longer accepts only `title`. A `project_id` is now required.

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

Omitting `project_id` returns `422 Unprocessable Entity`. You must provision a project first via your project management workflow, then include its ID when creating tasks.

---

### 6. List Response Format: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`.

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
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Update list-handling code to read from `.items` instead of the root array. To fetch subsequent pages, pass `?cursor=<next_cursor>` on the next request. The `limit` query parameter controls page size (default: 20).

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Change authentication header from `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] Update task ID handling to use UUID strings (not integers)
- [ ] Rename all `done` field references to `completed` in request and response code
- [ ] Add `project_id` to every task creation call (obtain project ID first)
- [ ] Update list response parsing to extract `items` from the envelope
- [ ] Add pagination logic using `next_cursor` for list endpoints
- [ ] Update database columns storing task IDs from integer to string type
- [ ] Run integration tests against v2 to verify all call sites updated

## Upgrade Command

```bash
zrb upgrade
```
