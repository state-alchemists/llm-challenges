# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Review each section, update your code to match the v2 patterns, and run the upgrade command at the end.

---

## 1. API Version Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1):**
```http
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

> **Impact:** Update every hard-coded URL or path builder in your client code.

---

## 2. Authentication Header

The `X-Auth-Token` header is removed. v2 requires a Bearer token in the `Authorization` header.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

> **Impact:** Sending `X-Auth-Token` in v2 returns **HTTP 401 Unauthorized**. Update your request middleware and environment variable names if they reference the old header.

---

## 3. Task `id` Changed from Integer to UUID

Task identifiers are now UUID strings instead of auto-incrementing integers.

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

> **Impact:** If your code casts `id` to `int`, stores it in integer columns, or uses it in numeric comparisons, switch to string handling immediately. URL paths such as `/v2/tasks/{id}` now expect a UUID string.

---

## 4. `done` Renamed to `completed`

The task status field is renamed from `done` to `completed`. Update request bodies and any destructuring logic.

**Before (v1):**
```http
PUT /tasks/42
Content-Type: application/json

{
  "title": "Updated title",
  "done": true
}
```

```javascript
const { done } = task;
```

**After (v2):**
```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Content-Type: application/json

{
  "title": "Updated title",
  "completed": true
}
```

```javascript
const { completed } = task;
```

> **Impact:** Any JSON payloads, filtering logic, or UI bindings referencing `done` must be renamed to `completed`.

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` in the request body. Omitting it returns **HTTP 422 Unprocessable Entity**.

**Before (v1):**
```http
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2):**
```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

> **Impact:** Inventory your task-creation calls and determine the correct `project_id` for each. If your application previously created tasks without a project context, you must now assign one explicitly.

---

## 6. List Endpoints Return Paginated Envelope

`GET /tasks` used to return a bare array. It now returns a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1):**
```http
GET /tasks
```

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```javascript
const tasks = await response.json();
console.log(tasks.length);        // 2
console.log(tasks[0].title);      // "Buy milk"
```

**After (v2):**
```http
GET /v2/tasks?limit=20
```

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

```javascript
const data = await response.json();
console.log(data.items.length);   // 2
console.log(data.items[0].title);  // "Buy milk"
console.log(data.total);           // 42

// Fetch next page
if (data.next_cursor) {
  await fetch(`/v2/tasks?cursor=${data.next_cursor}&limit=20`);
}
```

> **Impact:** Replace all direct array access on list responses with `data.items`. Implement cursor-based pagination if you need to fetch more than one page.

---

## Migration Checklist

Use this checklist to track your upgrade. Check each item off before running the final upgrade command.

- [ ] Update all endpoint URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] Migrate task `id` handling from integer to UUID string (database columns, path parameters, deserialization).
- [ ] Rename every occurrence of the `done` field to `completed` in request bodies, responses, and UI state.
- [ ] Add a valid `project_id` to every task creation request.
- [ ] Refactor list-task consumers to read `items` from the paginated envelope and support `cursor` pagination.
- [ ] Run your integration tests against the v2 endpoints and resolve any HTTP 401 or HTTP 422 errors.
- [ ] Update internal documentation and API client SDKs to reflect the new types and fields.

---

## Upgrade Command

Once your code is ready, install the v2 CLI:

```bash
zrb self upgrade
```

After upgrading, verify the version:

```bash
zrb --version
```

If you encounter issues, downgrade with `zrb self upgrade --version 1.x.x` while you finish the migration.
