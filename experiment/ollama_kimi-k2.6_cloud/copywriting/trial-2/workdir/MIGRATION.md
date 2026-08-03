# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change in Zrb CLI v2 and how to update your code.

---

## 1. API Version Prefix

All endpoints are now versioned under `/v2/`.

### Before (v1)

```bash
curl https://api.zrb.io/tasks
curl https://api.zrb.io/tasks/42
```

### After (v2)

```bash
curl https://api.zrb.io/v2/tasks
curl https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

The `X-Auth-Token` header is removed. Use a standard Bearer token in the `Authorization` header instead.

### Before (v1)

```bash
curl -H "X-Auth-Token: your_api_key" https://api.zrb.io/tasks
```

### After (v2)

```bash
curl -H "Authorization: Bearer your_api_token" https://api.zrb.io/v2/tasks
```

---

## 3. Task ID Type Changed from Integer to UUID

`id` is now a UUID string. Update any code that assumes an integer ID or performs numeric operations on task IDs.

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
console.log(taskId + 1); // 43
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
console.log(taskId); // string, not a number
```

---

## 4. Task Field `done` Renamed to `completed`

The `done` boolean field on task objects is now named `completed`. Update any JSON serialization, deserialization, or property access that references `done`.

### Before (v1)

```json
{
  "title": "Updated title",
  "done": true
}
```

```javascript
const isFinished = task.done;
```

### After (v2)

```json
{
  "title": "Updated title",
  "completed": true
}
```

```javascript
const isFinished = task.completed;
```

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Requests without it will return HTTP 422.

### Before (v1)

```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your_api_key" \
  -d '{"title": "New task"}'
```

### After (v2)

```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_api_token" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

---

## 6. List Endpoints Return Paginated Envelope

`GET /tasks` no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`.

### Before (v1)

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```javascript
const tasks = await response.json();
tasks.forEach(task => console.log(task.title));
```

### After (v2)

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
const tasks = data.items;
tasks.forEach(task => console.log(task.title));

// Fetch next page
const nextUrl = `https://api.zrb.io/v2/tasks?cursor=${data.next_cursor}`;
```

---

## Migration Checklist

Use this checklist to verify your migration is complete:

- [ ] Update all API base URLs to include `/v2/` prefix.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] Update task ID handling: replace integer logic with UUID string logic.
- [ ] Rename all references to `done` to `completed` in request/response payloads.
- [ ] Update task creation to include a required `project_id` field.
- [ ] Update list-task consumers to read from the `items` array inside the paginated envelope.
- [ ] Add pagination support using `cursor` and `limit` query parameters where needed.
- [ ] Run your test suite and verify no HTTP 401 or HTTP 422 errors remain.

---

## Upgrade Command

Upgrade the CLI to v2 via your package manager:

```bash
npm install -g zrb-cli@latest
```
