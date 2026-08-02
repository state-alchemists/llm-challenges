# Zrb CLI — v1 to v2 Migration Guide

This guide covers every breaking change between Zrb CLI v1 and v2, with before/after examples. Read it once, then work through the checklist at the end.

---

## Breaking Changes

### 1. URL Path Prefix

All endpoints now sit under `/v2/`.

**Before (v1):**
```bash
curl https://api.zrb.example/tasks
```

**After (v2):**
```bash
curl https://api.zrb.example/v2/tasks
```

---

### 2. Authentication Header

v1 used a custom header. v2 uses a standard Bearer token.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" \
     https://api.zrb.example/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
     https://api.zrb.example/v2/tasks
```

Requests sent with `X-Auth-Token` will now receive **HTTP 401**.

---

### 3. Task ID Type Changed

`id` is now a UUID string instead of an integer. If your code treats `id` as a number, parses it with `%d`, or stores it in an integer column, update it.

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

### 4. Field Rename: `done` → `completed`

The boolean flag indicating whether a task is finished has been renamed.

**Before (v1):**
```json
{ "done": true }
```

**After (v2):**
```json
{ "completed": true }
```

This affects:
- Reading task state from the response
- Sending updates in `PUT /v2/tasks/{id}`

---

### 5. Task Creation Now Requires `project_id`

Creating a task without a `project_id` now returns **HTTP 422**.

**Before (v1):**
```bash
curl -X POST https://api.zrb.example/tasks \
     -H "X-Auth-Token: <your_api_key>" \
     -H "Content-Type: application/json" \
     -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.example/v2/tasks \
     -H "Authorization: Bearer <your_api_token>" \
     -H "Content-Type: application/json" \
     -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

### 6. List Endpoints Return a Paginated Envelope

`GET /tasks` used to return a bare array. It now returns a paginated envelope with cursors.

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
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Pass `?cursor=<next_cursor>` to fetch the next page. `?limit=<number>` controls page size (default 20).

---

## Migration Checklist

Use this checklist to upgrade your codebase methodically.

1. **Upgrade the CLI**  
   Run the upgrade command at the bottom of this guide first.

2. **Update API credentials**  
   Switch from `X-Auth-Token` to `Authorization: Bearer <token>` in every request.

3. **Prefix all endpoint URLs**  
   Prepend `/v2/` to every path (`/tasks` → `/v2/tasks`, `/tasks/{id}` → `/v2/tasks/{id}`).

4. **Update task ID handling**  
   Change task ID type from integer to UUID string everywhere you parse, validate, store, or compare task IDs.

5. **Rename `done` to `completed`**  
   Search your codebase for `done` in task payloads and responses and rename to `completed`.

6. **Add `project_id` to task creation**  
   Provide a `project_id` field in every `POST /v2/tasks` call. Handle HTTP 422 for missing values.

7. **Adapt list-endpoint parsing**  
   Expect a paginated envelope instead of a bare array. Iterate over `items`, read `total`, and pass `next_cursor` to fetch subsequent pages.

8. **Run your test suite**  
   Verify everything still passes after the changes above.

---

## Upgrade Command

Install the latest CLI to pick up v2 support:

```bash
npm install -g @zrb/cli@latest
```
