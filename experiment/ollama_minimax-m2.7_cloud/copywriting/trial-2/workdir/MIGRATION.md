# Zrb CLI v1 → v2 Migration Guide

v2 introduces projects, cursor-based pagination, and stricter authentication. Several v1 conventions have changed. This guide covers every breaking change with before/after examples.

---

## Breaking Changes

### 1. Endpoint Prefix Changed

All endpoints are now under `/v2/`.

| v1 | v2 |
|---|---|
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

The auth header changed from a custom token header to a standard Bearer scheme.

| v1 | v2 |
|---|---|
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

### 3. Task `id` is Now a UUID String

Task IDs changed from auto-incrementing integers to UUID strings.

| v1 | v2 |
|---|---|
| `"id": 42` | `"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

Update any code that parses or stores task IDs to handle string values. URL path parameters for `GET /v2/tasks/{id}`, `PUT /v2/tasks/{id}`, and `DELETE /v2/tasks/{id}` now take UUID strings.

**Before (v1) — response:**
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z"}
```

**After (v2) — response:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
```

---

### 4. Task Field `done` Renamed to `completed`

The boolean completion flag was renamed.

| v1 | v2 |
|---|---|
| `"done": true` | `"completed": true` |

Update all request bodies and response parsing.

**Before (v1) — update request:**
```json
PUT /tasks/42
{"title": "Updated title", "done": true}
```

**After (v2) — update request:**
```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{"title": "Updated title", "completed": true}
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns **HTTP 422**.

**Before (v1) — create task:**
```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task"}'
```

**After (v2) — create task:**
```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer your_api_token" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

If you do not yet have a `project_id`, create a project first via `POST /v2/projects`.

---

### 6. List Response is Now Paginated

List endpoints return a pagination envelope instead of a bare array.

| v1 | v2 |
|---|---|
| `[{"id": 1, ...}, {"id": 2, ...}]` | `{"items": [...], "total": 42, "next_cursor": "cursor_xyz"}` |

Access the array via `response.items`. To paginate, pass `?cursor=<next_cursor>` on the next request.

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
    {"id": "e5f6a7b8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

To fetch the next page:
```bash
curl "https://api.zrb.dev/v2/tasks?cursor=cursor_xyz"
```

You can also set `?limit=<n>` to control page size (default 20).

---

## Migration Checklist

- [ ] Update all endpoint URLs: prepend `/v2/` to every task path
- [ ] Change auth header from `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] Update task ID handling: integers → UUID strings
- [ ] Replace all occurrences of field `done` with `completed` in request bodies and response parsing
- [ ] Add `project_id` to every task creation request (required field)
- [ ] Update list response parsing: access tasks via `response.items` instead of the root array
- [ ] Add pagination logic if your application iterates over list results
- [ ] Update any URL construction that interpolates task IDs to produce UUID strings
- [ ] Update persisted task IDs: integer IDs are no longer valid

---

## Upgrade Command

```bash
gem install zrb --version ">= 2.0.0"
```
