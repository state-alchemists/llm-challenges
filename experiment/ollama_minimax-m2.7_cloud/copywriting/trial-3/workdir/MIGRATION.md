# Zrb CLI v1 to v2 Migration Guide

v2 introduces projects, cursor-based pagination, and stricter authentication. Several v1 conventions have changed in breaking ways. This guide covers every breaking change with before/after examples and a step-by-step checklist to migrate your integration.

---

## Breaking Changes

### 1. All Endpoints Now Require `/v2/` Prefix

All endpoints are now versioned under `/v2/`.

| Operation | v1 | v2 |
|-----------|----|----|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**
```http
GET /tasks HTTP/1.1
Host: api.zrb.io
```

**After (v2):**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.io
```

---

### 2. Authentication Header Changed

The custom `X-Auth-Token` header is replaced with a standard Bearer token.

| | v1 | v2 |
|--|----|----|
| Header | `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` |
| Failure response | — | HTTP 401 |

Requests using `X-Auth-Token` will receive HTTP 401.

**Before (v1):**
```http
GET /tasks HTTP/1.1
Host: api.zrb.io
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.io
Authorization: Bearer your_api_token_here
```

---

### 3. Task `id` Changed from Integer to UUID String

Task IDs are no longer integers. They are now UUID strings.

| | v1 | v2 |
|--|----|----|
| `id` type | `42` (integer) | `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"` (string) |

This affects any code that parses, stores, or references task IDs.

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

### 4. Task Field `done` Renamed to `completed`

The boolean completion flag is renamed.

| | v1 | v2 |
|--|----|----|
| Field name | `done` | `completed` |

Update all references in your code, database columns, and serialized payloads.

**Before (v1):**
```json
{
  "id": 1,
  "title": "Buy milk",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Buy milk",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 5. Task Creation Requires `project_id`

A new `project_id` field is required when creating tasks. Omitting it returns HTTP 422.

| | v1 | v2 |
|--|----|----|
| Required fields | `title` | `title`, `project_id` |
| On omission | HTTP 201 | HTTP 422 |

**Before (v1):**
```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2):**
```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Endpoints Return Paginated Envelope

List responses are no longer bare arrays. They return a pagination envelope.

| | v1 | v2 |
|--|----|----|
| Response shape | `[...]` (array) | `{ "items": [...], "total": 42, "next_cursor": "cursor_xyz" }` |
| Pagination | None | Cursor-based via `?cursor=<next_cursor>` |
| Page size control | — | `?limit=N`, default 20 |

Update code that iterates over list responses to unwrap `items` from the envelope.

**Before (v1):**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2):**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 2,
  "next_cursor": null
}
```

---

## Migration Checklist

Follow these steps in order to migrate your v1 integration to v2.

- [ ] **1. Update endpoint base URL** — prepend `/v2/` to all task endpoints
- [ ] **2. Update authentication** — replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] **3. Update task ID handling** — change ID fields from integer to UUID string type in your code
- [ ] **4. Rename `done` to `completed`** — find and replace all occurrences in requests, responses, and storage
- [ ] **5. Add `project_id` to task creation** — include a valid `project_id` in every `POST /v2/tasks` body
- [ ] **6. Update list response parsing** — unwrap response arrays from `{ "items": [...] }` envelope; implement cursor pagination if you handle large lists
- [ ] **7. Update error handling** — `X-Auth-Token` requests now return 401; task creation without `project_id` returns 422
- [ ] **8. Test against v2 endpoint** — verify all CRUD operations work with a real v2 environment

---

## Upgrade Command

```bash
npm install zrb-cli@latest
```

Replace `zrb-cli` with your actual package manager package name if using pip, gem, go get, or another registry.
