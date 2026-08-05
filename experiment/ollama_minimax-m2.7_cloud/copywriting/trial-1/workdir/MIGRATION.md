# Zrb CLI Migration Guide: v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide walks through every breaking change with before/after examples and a step-by-step checklist to get you live.

## Breaking Changes

### 1. Endpoint Path Prefix

All endpoints now live under `/v2/`. Requests to v1 paths return 404.

**Before (v1)**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2)**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication Header

The auth header changed from `X-Auth-Token` to a Bearer token. Requests with the old header receive 401.

**Before (v1)**
```
X-Auth-Token: <your_api_key>
```

**After (v2)**
```
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type: Integer to UUID

Task `id` is now a UUID string. Integer IDs are no longer valid.

**Before (v1)**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2)**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Update any code that parses or stores task IDs to handle UUID strings instead of integers.

---

### 4. Field Renamed: `done` → `completed`

The `done` boolean is renamed to `completed`. The semantics are identical.

**Before (v1)**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2)**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns HTTP 422.

**Before (v1)**
```json
POST /tasks
{
  "title": "New task title"
}
```

**After (v2)**
```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Ensure your application resolves a `project_id` before creating tasks. See your project listing endpoint to fetch available project IDs.

---

### 6. List Response: Bare Array to Paginated Envelope

List endpoints return a pagination envelope instead of a bare array.

**Before (v1)**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2)**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>` on the request. The `limit` query param controls page size (default 20).

---

## Migration Checklist

Run through each step in order. Mark each done as you verify the change.

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Change auth header from `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] Replace any `done` field references with `completed` in request bodies and response parsing
- [ ] Update task ID parsing to expect UUID strings instead of integers
- [ ] Add `project_id` to all task creation requests (fetch project IDs first if needed)
- [ ] Update list response parsing to read `items` array from envelope, not the root array
- [ ] Implement cursor-based pagination if your application paginates through large task lists
- [ ] Point any stored task IDs or integrations at the new UUID format
- [ ] Run integration tests against the v2 endpoint
- [ ] Deploy and verify in staging

---

## Upgrade Command

```bash
# Pull the latest v2 CLI
npm install -g @zrb/cli@2

# Verify the version
zrb --version
```

For API users, update your base URL to `https://api.zrb.io/v2` and ensure your Authorization header uses the Bearer scheme.
