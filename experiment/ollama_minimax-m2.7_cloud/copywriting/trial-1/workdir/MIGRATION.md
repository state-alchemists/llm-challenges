# Zrb CLI Migration Guide: v1 → v2

v2 introduces several breaking changes. This guide walks through each one with before/after examples and a checklist to migrate your integration.

---

## Breaking Changes Overview

| # | Change | Summary |
|---|--------|---------|
| 1 | URL prefix | All endpoints moved from `/tasks` to `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token` replaced by `Authorization: Bearer <token>` |
| 3 | Task `id` type | Integer → UUID string |
| 4 | Task field `done` | Renamed to `completed` |
| 5 | Create Task requirement | `project_id` is now required |
| 6 | List response format | Bare array → paginated envelope |

---

## 1. URL Prefix

All endpoints are now under `/v2/`.

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

---

## 2. Authentication Header

The auth header has changed from a custom header to a standard Bearer token.

### Before (v1)

```http
X-Auth-Token: your_api_key_here
```

### After (v2)

```http
Authorization: Bearer your_api_token_here
```

> **Note:** Requests using `X-Auth-Token` will receive HTTP 401.

---

## 3. Task `id` Type

Task IDs are now UUID strings instead of integers. Update any code that parses or stores task IDs.

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

## 4. Task Field `done` Renamed to `completed`

The boolean completion flag has been renamed.

### Before (v1)

```json
{ "done": true }
```

### After (v2)

```json
{ "completed": true }
```

Update all request bodies and response handling.

---

## 5. Create Task Requires `project_id`

Task creation now requires a `project_id`. Omitting it returns HTTP 422.

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

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

## 6. List Response: Paginated Envelope

List endpoints no longer return a bare array. They return a wrapper envelope with `items`, `total`, and `next_cursor`.

### Before (v1)

```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

### After (v2)

```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>` on subsequent requests.

---

## Migration Checklist

- [ ] Update all endpoint URLs to use `/v2/` prefix
- [ ] Change auth header from `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] Update task ID handling: integer → UUID string
- [ ] Rename all `done` field references to `completed` in request bodies and response parsing
- [ ] Add `project_id` to all task creation calls
- [ ] Update list response parsing: unwrap `items` array from envelope, handle `total` and `next_cursor` for pagination
- [ ] Update any tests or mocks to reflect v2 data shapes
- [ ] Verify integration end-to-end

---

## Upgrade Command

```bash
rb task-cli upgrade
```

This updates your CLI and validates your current integration against v2 endpoints.
