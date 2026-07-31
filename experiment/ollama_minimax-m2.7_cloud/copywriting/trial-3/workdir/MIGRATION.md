# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Each section shows the v1 approach, the v2 replacement, and what you need to do.

---

## Breaking Changes

### 1. Endpoint Prefix Changed

All endpoints now live under `/v2/`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**
```http
GET /tasks HTTP/1.1
```

**After (v2):**
```http
GET /v2/tasks HTTP/1.1
```

---

### 2. Authentication Header Changed

The custom `X-Auth-Token` header is replaced with a standard Bearer token.

| v1 | v2 |
|---|---|
| `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` |

Requests with `X-Auth-Token` will receive **HTTP 401**.

**Before (v1):**
```http
GET /v2/tasks HTTP/1.1
X-Auth-Token: my_secret_key
```

**After (v2):**
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer my_secret_token
```

---

### 3. Task `id` Type Changed: Integer → UUID

Task IDs are no longer integers. They are now UUID strings.

| v1 | v2 |
|---|---|
| `"id": 42` | `"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

Update any code that parses or stores task IDs to expect a string. Database columns or variables typed as `int` must become `string`.

**Before (v1) — response:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — response:**
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

### 4. Task Field Renamed: `done` → `completed`

The `done` boolean is renamed to `completed`.

| v1 | v2 |
|---|---|
| `"done": true` | `"completed": true` |

Update all request bodies and response parsing.

**Before (v1) — update request:**
```json
PUT /tasks/42
{
  "done": true
}
```

**After (v2) — update request:**
```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{
  "completed": true
}
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` field. Omitting it returns **HTTP 422**.

| v1 | v2 |
|---|---|
| `POST /tasks` with `{"title": "..."}` | `POST /v2/tasks` with `{"title": "...", "project_id": "..."}` |

You must provision a project before creating tasks. Pass the project's ID (format: `proj_<string>`) on every create call.

**Before (v1) — create task:**
```http
POST /tasks
{
  "title": "New task"
}
```

**After (v2) — create task:**
```http
POST /v2/tasks
{
  "title": "New task",
  "project_id": "proj_abc123"
}
```

---

### 6. List Response Changed: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`.

| v1 | v2 |
|---|---|
| `[{"id": 1, ...}, {"id": 2, ...}]` | `{"items": [...], "total": 42, "next_cursor": "cursor_xyz"}` |

Update response parsing to read `response.items` instead of the root array. To page through results, pass `?cursor=<next_cursor>`.

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
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-f6a7-8901-bcde-f23456789012", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

Run through these steps in order:

- [ ] **1. Update endpoint base URL** — prepend `/v2` to every route (`/tasks` → `/v2/tasks`)
- [ ] **2. Update authentication header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **3. Update ID handling** — change task ID variables and database columns from `int` to `string` (UUID format)
- [ ] **4. Rename `done` field** — replace all occurrences of `"done"` with `"completed"` in request bodies and response parsing
- [ ] **5. Add `project_id` to task creation** — every `POST /v2/tasks` call must include `"project_id": "proj_..."`; provision a project first if needed
- [ ] **6. Update list response parsing** — read `response.items` instead of the root array; extract `total` and `next_cursor` for pagination
- [ ] **7. Update pagination logic** — use `?cursor=<next_cursor>` query param to fetch subsequent pages
- [ ] **8. Test against the v2 endpoint** — verify all CRUD operations work with the new shapes

---

## Upgrade Command

```bash
npm install -g zrb-cli@2
```

Replace `npm` with your package manager (`yarn`, `pnpm`, etc.) as appropriate.
