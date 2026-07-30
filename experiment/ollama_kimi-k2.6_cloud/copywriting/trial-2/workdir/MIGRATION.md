# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change you need to address when upgrading from v1.

---

## 1. API Endpoint Prefix

All endpoints are now prefixed with `/v2/`.

### Before (v1)
```
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

### After (v2)
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Action required:** Update all request URLs in your client code to include the `/v2/` prefix.

---

## 2. Authentication Header

The `X-Auth-Token` header is no longer accepted. v2 uses a Bearer token.

### Before (v1)
```
X-Auth-Token: <your_api_key>
```

### After (v2)
```
Authorization: Bearer <your_api_token>
```

**Action required:** Replace `X-Auth-Token` with `Authorization: Bearer <token>`. Requests using the old header will receive HTTP 401.

---

## 3. Task ID Type Changed

Task `id` has changed from an auto-assigned integer to a UUID string.

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

**Action required:** Update any code that stores or validates `id` as an integer. Treat task IDs as opaque strings.

---

## 4. Task Field Renamed: `done` → `completed`

The boolean field indicating task completion has been renamed.

### Before (v1)
```json
{
  "title": "Updated title",
  "done": true
}
```

### After (v2)
```json
{
  "title": "Updated title",
  "completed": true
}
```

**Action required:** Rename all references to the `done` field in request bodies and response parsing to `completed`.

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns HTTP 422.

### Before (v1)
```json
POST /tasks

{
  "title": "New task title"
}
```

### After (v2)
```json
POST /v2/tasks

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Action required:** Ensure your task creation flows collect or default a `project_id`, and include it in the request body.

---

## 6. List Endpoints Return Paginated Envelope

`GET /tasks` no longer returns a bare array. It now returns a paginated envelope with cursor-based navigation.

### Before (v1)
```json
GET /tasks

[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)
```json
GET /v2/tasks

{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the cursor as a query parameter:
```
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

**Action required:** Update list-consumption code to read from `response.items` instead of the root array. Implement cursor pagination if you need to traverse large result sets.

---

## Migration Checklist

Use this checklist to verify your upgrade before deploying to production.

- [ ] Update all endpoint URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] Update `id` storage/validation from integer to string (UUID).
- [ ] Rename all `done` fields to `completed` in request bodies and response parsing.
- [ ] Add `project_id` to all task creation requests.
- [ ] Update list-task consumers to read from the `items` envelope field.
- [ ] Implement cursor pagination for list endpoints (optional but recommended).
- [ ] Run integration tests against the v2 sandbox.
- [ ] Update internal documentation and client libraries.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g zrb-cli@latest
```

Verify the version:

```bash
zrb --version
```

You should see `2.x.x` or higher.
