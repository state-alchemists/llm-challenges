# Zrb CLI v1 to v2 Migration Guide

This guide covers every breaking change in Zrb CLI v2 and how to update your code. If you are already running on v1, follow the sections below in order.

---

## 1. Endpoint Prefix

**Breaking change:** All endpoints are now prefixed with `/v2/`.

Requests to the old unprefixed paths will not reach the v2 handlers.

### Before (v1)

```bash
curl https://api.zrb.io/tasks
curl https://api.zrb.io/tasks/42
curl -X POST https://api.zrb.io/tasks
curl -X PUT https://api.zrb.io/tasks/42
curl -X DELETE https://api.zrb.io/tasks/42
```

### After (v2)

```bash
curl https://api.zrb.io/v2/tasks
curl https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X POST https://api.zrb.io/v2/tasks
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Action:** Update every hard-coded URL or base path in your client configuration to include `/v2/`.

---

## 2. Authentication Header

**Breaking change:** The `X-Auth-Token` header is removed. v2 requires an `Authorization: Bearer` token.

Requests that still send `X-Auth-Token` will receive HTTP 401.

### Before (v1)

```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.io/tasks
```

### After (v2)

```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.io/v2/tasks
```

**Action:** Replace `X-Auth-Token` with `Authorization: Bearer` in every request.

---

## 3. Task `id` Changed from Integer to UUID

**Breaking change:** Task identifiers are no longer integers. Every `id` is now a UUID string.

If your client stores `id` as a number, parses it with `parseInt`, or builds URLs by concatenating an integer, those operations will fail.

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
// v1 client code
const taskId = 42;
const url = `/tasks/${taskId}`;
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
// v2 client code
const taskId = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
const url = `/v2/tasks/${taskId}`;
```

**Action:** Treat `id` as a string everywhere. Remove any integer parsing or numeric validation on the `id` field.

---

## 4. Task Field `done` Renamed to `completed`

**Breaking change:** The task status field is now named `completed`. The old field name `done` is no longer accepted in request bodies and will not appear in responses.

### Before (v1)

**Response body:**
```json
{
  "id": 42,
  "title": "Ship v1",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Update request:**
```bash
curl -X PUT https://api.zrb.io/tasks/42 \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"done": true}'
```

### After (v2)

**Response body:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Ship v1",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Update request:**
```bash
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"completed": true}'
```

**Action:** Rename every occurrence of `done` to `completed` in request bodies, response parsing, and local model types.

---

## 5. Task Creation Now Requires `project_id`

**Breaking change:** Creating a task without a `project_id` returns HTTP 422.

### Before (v1)

```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

### After (v2)

```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

**Action:** Ensure your task-creation logic knows the target `project_id` and includes it in the JSON body. If your application currently has no concept of projects, create a default project in the Zrb dashboard and use its ID.

---

## 6. List Endpoints Return a Paginated Envelope

**Breaking change:** `GET /tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`.

If your code expects an array and directly iterates over the top-level response, it will break.

### Before (v1)

**Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```javascript
// v1 client code
const tasks = await response.json();
for (const task of tasks) {
  console.log(task.title);
}
```

### After (v2)

**Response:**
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

```javascript
// v2 client code
const page = await response.json();
for (const task of page.items) {
  console.log(task.title);
}

if (page.next_cursor) {
  const nextPage = await fetch(`/v2/tasks?cursor=${page.next_cursor}`);
}
```

**Action:** Update all list-consumption code to read from `response.items` instead of treating the response body as an array. Add pagination logic if you need to fetch more than one page.

---

## Migration Checklist

Use this checklist to verify that your upgrade is complete:

- [ ] Update base URL or route prefix to include `/v2/` on every endpoint.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] Change task `id` handling from integer to string (UUID) everywhere.
- [ ] Rename all references to the `done` field to `completed`.
- [ ] Add `project_id` to every task creation request.
- [ ] Update list-endpoint consumers to read `items` from the paginated envelope.
- [ ] Add pagination support (cursor-based) if your UI needs full list traversal.
- [ ] Run your test suite against the v2 endpoints.
- [ ] Update API client types, mocks, and fixtures to match v2 shapes.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g zrb-cli@latest
```

After installation, confirm the version:

```bash
zrb --version
```

You should see `2.x.x`. If you are pinned to v1 in `package.json`, update the dependency version and run `npm install`.
