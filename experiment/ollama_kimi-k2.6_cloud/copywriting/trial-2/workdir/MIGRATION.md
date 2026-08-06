# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. It assumes you are already familiar with v1 and have an existing integration in place.

---

## Overview of Breaking Changes

Zrb CLI v2 introduces the following breaking changes:

1. [All endpoints are now prefixed with `/v2/`](#endpoint-prefix)
2. [Authentication header changed to Bearer token](#authentication)
3. [Task `id` type changed from integer to UUID string](#task-id-type)
4. [Task field `done` renamed to `completed`](#task-field-renamed)
5. [Task creation now requires `project_id`](#task-creation-requires-project-id)
6. [List endpoints return a paginated envelope instead of a bare array](#list-endpoints-pagination)

---

## Endpoint Prefix

**Breaking change:** All API endpoints are now prefixed with `/v2/`. Requests to the old unprefixed paths will not be recognized.

### Before (v1)

```bash
curl -X GET "https://api.zrb.example/tasks"
```

### After (v2)

```bash
curl -X GET "https://api.zrb.example/v2/tasks"
```

---

## Authentication

**Breaking change:** The `X-Auth-Token` header is no longer accepted. v2 uses a standard `Authorization: Bearer <token>` header. Requests using the old header will receive HTTP 401.

### Before (v1)

```bash
curl -H "X-Auth-Token: <your_api_key>" \
  -X GET "https://api.zrb.example/tasks"
```

### After (v2)

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  -X GET "https://api.zrb.example/v2/tasks"
```

---

## Task `id` Type

**Breaking change:** Task identifiers have changed from auto-incrementing integers to UUID strings. Update any client-side code that assumes `id` is numeric or performs integer comparisons.

### Before (v1)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

```javascript
// v1: id is an integer
const taskId = 42;
fetch(`/tasks/${taskId}`);
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

```javascript
// v2: id is a UUID string
const taskId = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
fetch(`/v2/tasks/${taskId}`);
```

---

## Task Field Renamed: `done` → `completed`

**Breaking change:** The boolean field `done` on task objects has been renamed to `completed`. Update all request payloads and response parsing that reference `done`.

### Before (v1)

```json
{
  "title": "Updated title",
  "done": true
}
```

```javascript
// v1 response parsing
const isDone = response.done;
```

### After (v2)

```json
{
  "title": "Updated title",
  "completed": true
}
```

```javascript
// v2 response parsing
const isDone = response.completed;
```

---

## Task Creation Requires `project_id`

**Breaking change:** Creating a task now requires a `project_id` field in the request body. Omitting it will return HTTP 422.

### Before (v1)

```bash
curl -X POST "https://api.zrb.example/tasks" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

### After (v2)

```bash
curl -X POST "https://api.zrb.example/v2/tasks" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

## List Endpoints Return Paginated Envelope

**Breaking change:** The `GET /tasks` endpoint no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`.

Use `?cursor=<next_cursor>` to fetch subsequent pages.

### Before (v1)

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```javascript
// v1: direct array iteration
const tasks = await response.json();
tasks.forEach(task => console.log(task.title));
```

### After (v2)

```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "b2c3d4e5-f6a7-8901-bcde-f12345678901", "title": "Ship v2", "completed": true, "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

```javascript
// v2: access the items array inside the envelope
const data = await response.json();
data.items.forEach(task => console.log(task.title));

// v2: pagination
const nextPageUrl = `/v2/tasks?cursor=${data.next_cursor}`;
```

---

## Migration Checklist

Use this checklist to upgrade your integration safely:

- [ ] **Update base URL paths** — prepend `/v2/` to all endpoint paths (`/tasks` → `/v2/tasks`, `/tasks/{id}` → `/v2/tasks/{id}`, etc.).
- [ ] **Replace authentication header** — change `X-Auth-Token: <key>` to `Authorization: Bearer <token>`.
- [ ] **Migrate task identifiers** — update all variables, types, and storage that assume `id` is an integer; treat it as a UUID string instead.
- [ ] **Rename `done` to `completed`** — update request payloads for task creation and updates, and all response parsing logic.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` request includes a valid `project_id`.
- [ ] **Adapt list responses** — wrap existing array logic to read from the `items` key and implement cursor-based pagination using `next_cursor`.
- [ ] **Run integration tests** — verify all endpoints against the v2 API in a staging environment before deploying to production.

---

## Upgrade Command

Install or upgrade to v2 via your package manager:

```bash
pip install --upgrade zrb-cli>=2.0.0
```

Or via Homebrew:

```bash
brew update && brew upgrade zrb-cli
```

After upgrading, confirm the version:

```bash
zrb --version
```
