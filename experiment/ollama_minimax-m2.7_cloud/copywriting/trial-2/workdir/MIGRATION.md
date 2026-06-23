# Migration Guide: Zrb Task API v1 → v2

This guide covers every breaking change when upgrading from v1 to v2, with before/after examples and a step-by-step checklist.

## Overview

v2 introduces projects, improved pagination, and stricter auth. All v1 integrations will need changes.

## Breaking Changes

### 1. Endpoint Prefix Changed

All endpoints now include `/v2/` prefix.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before:**
```bash
curl https://api.zrb.dev/tasks
```

**After:**
```bash
curl https://api.zrb.dev/v2/tasks
```

---

### 2. Authentication Header Changed

The auth header changed from a custom header to a standard Bearer token.

| v1 | v2 |
|---|---|
| `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |

Requests using `X-Auth-Token` will receive **HTTP 401**.

**Before:**
```bash
curl -H "X-Auth-Token: my_api_key" https://api.zrb.dev/tasks
```

**After:**
```bash
curl -H "Authorization: Bearer my_api_token" https://api.zrb.dev/v2/tasks
```

---

### 3. Task `id` Type Changed: Integer → UUID

Task IDs are no longer integers. They are now UUID strings.

| v1 | v2 |
|---|---|
| `"id": 42` | `"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

Any code that treats `id` as an integer (sorting, incrementing, etc.) will break.

**Before:**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123" }
```

---

### 4. Field Renamed: `done` → `completed`

The boolean completion flag is renamed.

| v1 | v2 |
|---|---|
| `done` | `completed` |

Update all references to this field.

**Before:**
```json
{ "id": 1, "title": "Ship v1", "done": true }
```

**After:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Ship v2", "completed": true, "project_id": "proj_abc123" }
```

For updates, the field name in the request body also changes:

**Before:**
```json
PUT /tasks/42
{ "done": true }
```

**After:**
```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{ "completed": true }
```

---

### 5. Task Creation Requires `project_id`

Tasks can no longer be created without a project. Omitting `project_id` returns **HTTP 422**.

**Before:**
```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: my_api_key" \
  -d '{ "title": "New task" }'
```

**After:**
```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer my_api_token" \
  -d '{ "title": "New task", "project_id": "proj_abc123" }'
```

Response body change:
**Before:**
```json
{ "id": 42, "title": "New task", "done": false, "created_at": "..." }
```

**After:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "New task", "completed": false, "project_id": "proj_abc123", "created_at": "..." }
```

---

### 6. List Response: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return an envelope with `items`, `total`, and `next_cursor`.

**Before:**
```json
[
  { "id": 1, "title": "Buy milk", "done": false },
  { "id": 2, "title": "Ship v1", "done": true }
]
```

**After:**
```json
{
  "items": [
    { "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123" },
    { "id": "b2c3d4e5-f6a7-8901-bcde-f23456789012", "title": "Ship v2", "completed": true, "project_id": "proj_abc123" }
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

Access items as `response.items` instead of `response` directly.

Pagination: pass `?cursor=<next_cursor>` to fetch the next page. Use `?limit=N` to control page size (default 20).

---

## Step-by-Step Migration Checklist

- [ ] Update all endpoint URLs: add `/v2/` prefix
- [ ] Change auth header from `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] Update task `id` handling: expect UUID strings, not integers
- [ ] Rename all `done` field references to `completed`
- [ ] Add required `project_id` field to all task creation calls
- [ ] Update list response parsing: read `response.items` instead of `response` directly
- [ ] Add pagination handling: check `response.next_cursor` and implement cursor-based pagination if listing many tasks
- [ ] Update any code that serializes task objects (JSON serialization of `done` vs `completed`)
- [ ] Run integration tests against v2 endpoint

## Upgrade Command

```bash
pip install --upgrade zrb>=2.0.0
```