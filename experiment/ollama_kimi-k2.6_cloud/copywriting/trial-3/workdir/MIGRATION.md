# Zrb CLI v1 → v2 Migration Guide

Zrb CLI v2 introduces projects, improved pagination, and stricter authentication. This guide covers every breaking change you need to address when upgrading from v1.

If you are already running v1 in production, review each section below, update your integration code, and run through the checklist at the end before deploying.

---

## 1. Endpoint paths are now prefixed with `/v2/`

All API endpoints have moved under the `/v2/` namespace. Requests to the old bare paths will return HTTP 404.

### Before (v1)
```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

### After (v2)
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication header changed to Bearer token

The `X-Auth-Token` header is no longer accepted. v2 requires an `Authorization` header with a Bearer token. Requests using the old header will receive HTTP 401.

### Before (v1)
```http
X-Auth-Token: <your_api_key>
```

### After (v2)
```http
Authorization: Bearer <your_api_token>
```

---

## 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of auto-incrementing integers. If your client code stores task IDs in integer-typed variables or databases, update those schemas to strings.

### Before (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

## 4. Task field `done` renamed to `completed`

The boolean status field on task objects has been renamed from `done` to `completed`. Update any deserialization, filtering, or UI logic that references the old field name.

### Before (v1)
```json
{
  "title": "Ship v2",
  "done": true
}
```

### After (v2)
```json
{
  "title": "Ship v2",
  "completed": true
}
```

---

## 5. Task creation now requires `project_id`

Creating a task without a `project_id` now returns HTTP 422. You must include a valid project identifier in every create request.

### Before (v1)
```http
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

### After (v2)
```http
POST /v2/tasks
Content-Type: application/json
Authorization: Bearer <your_api_token>

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

## 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`. You must update parsing logic to unwrap the `items` array, and handle pagination via the `cursor` query parameter.

### Before (v1)
**Request:**
```http
GET /tasks
```

**Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)
**Request:**
```http
GET /v2/tasks?limit=20
Authorization: Bearer <your_api_token>
```

**Response:**
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

Fetch subsequent pages by passing `?cursor=<next_cursor>`.

---

## Migration Checklist

Use this checklist to verify your upgrade before going live.

- [ ] Update base URL or client configuration to prepend `/v2/` to all task endpoints.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] Change task ID storage from integer to string (UUID) in your database, models, and URL routing.
- [ ] Rename all references from `done` to `completed` in deserialization, serialization, and UI code.
- [ ] Add `project_id` to every task creation payload and ensure valid project identifiers are available.
- [ ] Update list-task parsing to read from the `items` key in the paginated envelope.
- [ ] Implement cursor-based pagination for list endpoints using `next_cursor` and the `cursor` query parameter.
- [ ] Run your test suite against the v2 endpoints.
- [ ] Deploy to staging and verify end-to-end task flows.

---

## Upgrade Command

Install the latest v2 release globally:

```bash
npm install -g zrb-cli@latest
```

Or upgrade your local project dependency:

```bash
npm install zrb-cli@latest
```

After upgrading, validate your installation:

```bash
zrb --version
```
