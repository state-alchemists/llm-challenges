# Zrb Task API — Migration Guide v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide walks you through every breaking change with before/after examples and a step-by-step checklist to get you running on v2 quickly.

---

## Breaking Changes

### 1. Endpoint Prefix Changed

All endpoints are now versioned under `/v2/`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**
```bash
curl https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl https://api.zrb.io/v2/tasks
```

---

### 2. Authentication Header Changed

The auth header switched from a custom header to a standard Bearer token.

| v1 | v2 |
|---|---|
| `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` |

Requests using the old `X-Auth-Token` header will receive **HTTP 401**.

**Before (v1):**
```bash
curl -H "X-Auth-Token: sk_live_abc123" https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer sk_live_abc123" https://api.zrb.io/v2/tasks
```

---

### 3. Task `id` Type Changed: Integer to UUID

Task IDs are now UUID strings instead of integers. Update any code that parses or stores task IDs.

| v1 | v2 |
|---|---|
| `"id": 42` | `"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

**Before (v1) — response:**
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z"}
```

**After (v2) — response:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
```

---

### 4. Task Field Renamed: `done` → `completed`

The `done` boolean is now `completed`.

| v1 | v2 |
|---|---|
| `"done": true` | `"completed": true` |

**Before (v1) — update request:**
```bash
curl -X PUT https://api.zrb.io/tasks/42 \
  -H "X-Auth-Token: sk_live_abc123" \
  -d '{"done": true}'
```

**After (v2) — update request:**
```bash
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer sk_live_abc123" \
  -d '{"completed": true}'
```

---

### 5. Task Creation Requires `project_id`

Create requests must now include a `project_id`. Omitting it returns **HTTP 422**.

**Before (v1) — create request:**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "X-Auth-Token: sk_live_abc123" \
  -d '{"title": "New task"}'
```

**After (v2) — create request:**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer sk_live_abc123" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

---

### 6. List Response Format: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They now return a pagination envelope with `items`, `total`, and `next_cursor`.

| v1 | v2 |
|---|---|
| `[{...}, {...}]` | `{"items": [{...}], "total": 42, "next_cursor": "cursor_xyz"}` |

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
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Use `?cursor=<next_cursor>` to fetch subsequent pages and `?limit=N` to control page size (default: 20).

---

## Migration Checklist

Run through these steps in order. Mark each done as you complete it.

- [ ] **Update endpoint base URL** — prepend `/v2` to every task endpoint path
- [ ] **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer`
- [ ] **Update task ID handling** — change ID fields from `int` to `str` (UUID); update any database columns, serialization, or cache keys
- [ ] **Rename `done` → `completed`** — search for `.done` and `done=` in your codebase; update to `.completed` and `completed=`
- [ ] **Add `project_id` to task creation** — every `POST /v2/tasks` body must include `"project_id": "<your_project_id>"`; obtain project IDs from your account dashboard or the projects API
- [ ] **Update list response parsing** — change code that reads a bare array to read `.items`, `.total`, and `.next_cursor`; implement cursor-based pagination loop if you iterate over all results
- [ ] **Update integration tests** — point test fixtures and mocks at v2 endpoints and updated response shapes
- [ ] **Verify with a smoke test** — create a task, read it back, update it, delete it

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g zrb@latest
```

Or, if you use a project-local installation:

```bash
npm install zrb@latest
```

After upgrading, re-authenticate if needed:

```bash
zrb auth login
```

Then re-run your integration suite to confirm everything passes against v2.
