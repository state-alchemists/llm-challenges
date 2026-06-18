# Zrb CLI v1 to v2 Migration Guide

v2 introduces projects, improved pagination, and stricter auth. This guide walks through every breaking change with before/after examples.

## Breaking Changes

### 1. Endpoint Prefix Changed

All endpoints now live under `/v2/`.

| v1 | v2 |
|----|----|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**
```bash
curl https://api.zrb.dev/tasks
```

**After (v2):**
```bash
curl https://api.zrb.dev/v2/tasks
```

---

### 2. Authentication Header Changed

The auth header switched from a custom header to a standard Bearer token.

| v1 | v2 |
|----|----|
| `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` |

Requests using `X-Auth-Token` will receive **HTTP 401**.

**Before (v1):**
```bash
curl -H "X-Auth-Token: your_api_key" https://api.zrb.dev/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer your_api_token" https://api.zrb.dev/v2/tasks
```

---

### 3. Task ID Type Changed: Integer to UUID

Task `id` is now a UUID string instead of an integer.

| v1 | v2 |
|----|----|
| `"id": 42` | `"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

Update any code that parses or stores task IDs to handle UUID strings.

**Before (v1) — response:**
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z"}
```

**After (v2) — response:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
```

---

### 4. Field Renamed: `done` → `completed`

The `done` boolean field is renamed to `completed`.

| v1 | v2 |
|----|----|
| `"done": true` | `"completed": true` |

**Before (v1) — update request:**
```bash
curl -X PUT https://api.zrb.dev/tasks/42 \
  -H "X-Auth-Token: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

**After (v2) — update request:**
```bash
curl -X PUT https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer your_api_token" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

---

### 5. Create Task Requires `project_id`

Task creation now requires a `project_id` field. Omitting it returns **HTTP 422**.

**Before (v1) — create request:**
```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task"}'
```

**After (v2) — create request:**
```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer your_api_token" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

---

### 6. List Response Format: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1) — list response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) — list response:**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>`:

```bash
curl "https://api.zrb.dev/v2/tasks?cursor=cursor_xyz&limit=20" \
  -H "Authorization: Bearer your_api_token"
```

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Change auth header from `X-Auth-Token` to `Authorization: Bearer`
- [ ] Update task ID handling to use UUID strings (not integers)
- [ ] Rename all `done` field references to `completed`
- [ ] Add `project_id` to all task creation calls
- [ ] Update list response parsing to handle the envelope `{items, total, next_cursor}`
- [ ] Implement cursor-based pagination if you fetch multiple pages
- [ ] Update any stored task ID data types

---

## Upgrade Command

```bash
# Update your zrb CLI to v2
pip install --upgrade zrb
```
