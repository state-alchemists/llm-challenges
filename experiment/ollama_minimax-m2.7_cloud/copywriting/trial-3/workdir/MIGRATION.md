# Zrb CLI Migration Guide: v1 → v2

v2 introduces projects, pagination, and stricter authentication — along with several breaking changes. This guide walks through each change with before/after examples and a step-by-step checklist to get you running on v2.

---

## Breaking Changes

### 1. Endpoint Prefix Changed to `/v2/`

All endpoints now live under `/v2/`. Requests to the old `/tasks` prefix will receive HTTP 404.

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

### 2. Authentication Header Changed

The `X-Auth-Token` header is no longer accepted. v2 uses Bearer token authentication.

**Before (v1)**
```http
X-Auth-Token: <your_api_key>
```

**After (v2)**
```http
Authorization: Bearer <your_api_token>
```

Old requests using `X-Auth-Token` will receive HTTP 401.

---

### 3. Task `id` Type Changed from Integer to UUID String

Task IDs are no longer integers. They are now UUID strings.

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

Update any code that parses or stores task IDs — integer assumptions will break.

---

### 4. Task Field `done` Renamed to `completed`

The `done` boolean is now called `completed`.

**Before (v1) — Update Task request body**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) — Update Task request body**
```json
{
  "title": "Updated title",
  "completed": true
}
```

Update field references in JSON serialization, deserialization, and any database schemas.

---

### 5. Task Creation Now Requires `project_id`

Creating a task without a `project_id` now returns HTTP 422. The field is required.

**Before (v1) — Create Task**
```json
{
  "title": "New task title"
}
```

**After (v2) — Create Task**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

You must provision a project before creating tasks. See your project dashboard or API to obtain a `project_id`.

---

### 6. List Endpoints Return Paginated Envelope Instead of Bare Array

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`.

**Before (v1) — List Tasks response**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) — List Tasks response**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

To paginate, pass `?cursor=<next_cursor>` on the next request. Set `?limit=<n>` to control page size (default 20).

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Change authentication header from `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] Update task ID handling — parse IDs as strings, not integers
- [ ] Rename all `done` field references to `completed`
- [ ] Add `project_id` to all task creation requests
- [ ] Update list response parsing — extract `items` from the envelope
- [ ] Handle pagination with `next_cursor` for large result sets
- [ ] Test against the v2 endpoint before deploying

---

## Upgrade Command

Replace your v1 package with v2:

```bash
npm install @zrb/cli@2
```

Or via your package manager:

```bash
yarn add @zrb/cli@2
# or
pnpm add @zrb/cli@2
```
