# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change between Zrb CLI v1 and v2. If you are currently on v1, follow the sections below and the checklist at the end to upgrade safely.

---

## 1. Endpoint Prefix Required

All endpoints are now prefixed with `/v2/`. Requests to the old unversioned paths will return HTTP 404.

**Before (v1):**
```
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**
```
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header Changed

v1 used a custom header with your API key. v2 uses a standard Bearer token. Requests sent with the old `X-Auth-Token` header will receive HTTP 401.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

---

## 3. Task `id` Type Changed from Integer to UUID String

Task identifiers are no longer integers. They are UUID strings across all endpoints and in every response body. Update any client-side logic that assumes `id` is a number.

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

---

## 4. Task Field `done` Renamed to `completed`

The boolean status field on task objects and in update payloads has been renamed. Using `done` in a request body will be ignored or rejected.

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

---

## 5. Task Creation Now Requires `project_id`

Creating a task without a `project_id` will return HTTP 422. You must include it in every create request.

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

---

## 6. List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope. You must extract the `items` array from the response and handle `next_cursor` for pagination.

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
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-f6a7-8901-bcde-f12345678901", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>`.

---

## Migration Checklist

Use this checklist to verify your upgrade:

- [ ] Update all request URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] Update any client-side data types or validation so task `id` is treated as a UUID string instead of an integer.
- [ ] Rename every usage of the `done` field to `completed` in request bodies and response parsing.
- [ ] Add `project_id` to every task creation request.
- [ ] Update list-task consumers to read `response.items` instead of the bare array and implement cursor-based pagination using `response.next_cursor`.
- [ ] Run your test suite against the v2 endpoints and fix any HTTP 401, 404, or 422 responses.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
pip install --upgrade zrb>=2.0.0
```

After upgrading, re-authenticate if your token format has changed:

```bash
zrb login --token "<your_api_token>"
```
