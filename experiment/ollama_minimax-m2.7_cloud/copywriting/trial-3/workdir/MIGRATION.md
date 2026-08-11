# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Each section shows exactly what changed and the code needed to update.

## Breaking Changes Overview

| # | Change | Impact |
|---|--------|--------|
| 1 | All endpoints prefixed with `/v2/` | Update all URL paths |
| 2 | Auth header: `X-Auth-Token` → `Bearer` token | Update request headers |
| 3 | Task `id` is now a UUID string | Update data type handling |
| 4 | Field `done` renamed to `completed` | Update field names in code |
| 5 | `project_id` is now required on task creation | Add required field to create payloads |
| 6 | List endpoints return paginated envelope | Update response parsing |

---

## 1. Endpoint Prefix: `/` → `/v2/`

All endpoints now live under the `/v2/` path prefix.

**Before (v1):**
```http
GET /tasks
POST /tasks
GET /tasks/42
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

The authentication header has changed from a custom header to a standard Bearer token scheme.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

Requests using `X-Auth-Token` will now receive **HTTP 401 Unauthorized**.

---

## 3. Task `id` Type: Integer → UUID String

Task IDs are no longer integers. They are now UUID strings.

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

Update any code that parses or stores task IDs to expect a string in UUID format, not an integer.

---

## 4. Field Renamed: `done` → `completed`

The task completion field has been renamed.

**Before (v1):**
```json
{ "title": "Ship v1", "done": true }
```

**After (v2):**
```json
{ "title": "Ship v2", "completed": true }
```

Update all references to this field in:
- Request bodies (update and create payloads)
- Response parsing logic
- Conditional checks (`task.done` → `task.completed`)

---

## 5. New Required Field: `project_id`

Task creation now requires a `project_id`. This is a new concept in v2 — tasks must belong to a project.

**Before (v1):**
```json
{ "title": "New task title" }
```

**After (v2):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Omitting `project_id` returns **HTTP 422 Unprocessable Entity**.

You will need to:
1. Determine how to obtain or create project IDs for your use case
2. Include `project_id` in every task creation request

---

## 6. List Response Format: Array → Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope.

**Before (v1):**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2):**
```json
{
  "items": [
    { "id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..." },
    { "id": "...", "title": "Ship v2", "completed": true, "project_id": "...", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, pass `?cursor=<next_cursor>`.

Update response handling to extract `items` from the envelope rather than using the response body directly.

---

## Migration Checklist

Use this checklist to migrate your integration:

- [ ] **Update base URL** — add `/v2` prefix to all endpoint paths
- [ ] **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update ID handling** — change task ID variables/data from `int` to `string` (UUID format)
- [ ] **Rename `done` field** — find/replace `done` → `completed` in all request/response code
- [ ] **Add `project_id` to task creation** — include a valid `project_id` in every create request
- [ ] **Update list response parsing** — extract `items` from the paginated envelope; update pagination logic to use `next_cursor`
- [ ] **Test with v2 API** — verify all CRUD operations work against the live v2 endpoint

---

## Upgrade Command

To install Zrb CLI v2:

```bash
npm install -g zrb-cli@2
```

Or, if you prefer yarn:

```bash
yarn global add zrb-cli@2
```

---

For full API reference, see [v2_spec.md](./v2_spec.md).
