# Zrb CLI Migration Guide: v1 → v2

v2 introduces projects, cursor-based pagination, and stricter authentication. It is a breaking release — several fields, headers, and response shapes have changed.

**Estimated migration time:** 30–60 minutes, depending on the depth of your v1 integration.

---

## Breaking Changes

### 1. URL Prefix Changed

All endpoints are now prefixed with `/v2/`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before:**
```http
GET /tasks HTTP/1.1
Host: api.zrb.io
```

**After:**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.io
```

---

### 2. Authentication Header Changed

The `X-Auth-Token` header is no longer accepted. Replace it with a Bearer token in the `Authorization` header.

| v1 | v2 |
|---|---|
| `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` |

Requests with `X-Auth-Token` will receive **HTTP 401 Unauthorized**.

**Before:**
```http
GET /tasks HTTP/1.1
Host: api.zrb.io
X-Auth-Token: your_api_key_here
```

**After:**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.io
Authorization: Bearer your_api_token_here
```

---

### 3. Task `id` Is Now a UUID String

Task IDs changed from auto-incrementing integers to UUID strings.

| v1 | v2 |
|---|---|
| `"id": 42` | `"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

Your code must treat `id` as a string, not an integer. Any URL path segments or database columns holding task IDs must be updated accordingly.

**Before (task object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (task object):**
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

### 4. Field Renamed: `done` → `completed`

The boolean completion flag is renamed from `done` to `completed`. Update all references in your request bodies, response handling, and any persisted copies.

**Before (update request):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (update request):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` field. Omitting it returns **HTTP 422 Unprocessable Entity**.

You must provision at least one project before creating tasks. See [Projects](#projects) for the new project endpoints.

**Before (create task):**
```json
{
  "title": "New task title"
}
```

**After (create task):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Responses Are Paginated

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`.

To fetch subsequent pages, pass `?cursor=<next_cursor>`.

| v1 | v2 |
|---|---|
| `[{"id": 1, ...}, {"id": 2, ...}]` | `{"items": [...], "total": 42, "next_cursor": "cursor_xyz"}` |

**Before (list response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (list response):**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6a7b8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Projects

v2 introduces projects as a top-level resource. Tasks must belong to a project.

| Action | Endpoint |
|---|---|
| List projects | `GET /v2/projects` |
| Create project | `POST /v2/projects` |

Project IDs are strings with a `proj_` prefix (e.g., `proj_abc123`).

---

## Migration Checklist

Run through each step in order. Mark each item done as you complete it.

- [ ] **Update all endpoint URLs** — prepend `/v2` to every task endpoint path
- [ ] **Replace the auth header** — change `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] **Update `id` handling** — treat task IDs as strings (UUID), not integers
- [ ] **Rename `done` to `completed`** — in request bodies, response parsing, and any stored data
- [ ] **Provision projects** — call `POST /v2/projects` to create at least one project
- [ ] **Add `project_id` to task creation** — every create request must include `project_id`
- [ ] **Update list response parsing** — access tasks via `response.items`, not the response root
- [ ] **Implement cursor pagination** — use `response.next_cursor` with `?cursor=` for subsequent pages
- [ ] **Update client libraries and SDKs** — ensure bindings generate UUID types and updated response shapes
- [ ] **Run integration tests** — verify your integration works end-to-end against the v2 endpoints

---

## Upgrade Command

Replace your v1 client with the v2 package:

```bash
npm install zrb@latest
```

For other package managers:

```bash
# Yarn
yarn add zrb@latest

# pip
pip install --upgrade zrb
```
