# Migrating from Zrb API v1 to v2

v2 introduces projects, cursor-based pagination, stricter authentication, and several breaking changes to the task model. This guide covers every change you need to make to move from v1 to v2.

**Upgrade path:** v2 runs alongside v1 during the deprecation period. Both APIs are live; direct your integration at `/v2/` when ready.

---

## Breaking Changes

### 1. Authentication Header

`X-Auth-Token` is removed. Requests using it receive HTTP 401. Use a Bearer token instead.

**v1 (old):**
```http
X-Auth-Token: sk-abc123
```

**v2 (new):**
```http
Authorization: Bearer zrb_api_prod_abc123def456
```

To obtain a Bearer token, see the [Authentication Guide](https://docs.zrb.dev/auth). Each token is scoped to a specific project.

---

### 2. Endpoint Prefix: `/v2/`

All endpoints now live under `/v2/`. The bare `/tasks` path returns HTTP 404 in v2.

**v1 (old):**
```
GET /tasks
POST /tasks
GET /tasks/42
PUT /tasks/42
DELETE /tasks/42
```

**v2 (new):**
```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 3. Task `id` Type: Integer → UUID String

Task identifiers are now UUID v4 strings. Existing integer IDs are not migrated to v2 — you must re-fetch tasks by their new UUID.

**v1 (old):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**v2 (new):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Update any stored references, URL construction, or type assertions that assume an integer `id`. Treat the new UUID as opaque — don't parse fields from it.

---

### 4. Task Field Rename: `done` → `completed`

The boolean status field is renamed from `done` to `completed`. The semantics are identical.

**v1 (old):** Creating a task:
```json
{
  "title": "Refactor auth module",
  "done": false
}
```

**v2 (new):**
```json
{
  "title": "Refactor auth module",
  "completed": false,
  "project_id": "proj_abc123"
}
```

Update all reads and writes of this field in your codebase. If you have client-side type definitions or mocks, rename the field there too.

---

### 5. Creating Tasks Now Requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns HTTP 422 with a validation error.

**v1 (old):**
```json
POST /tasks
{
  "title": "Deploy to staging"
}
```

**v2 (new):**
```json
POST /v2/tasks
{
  "title": "Deploy to staging",
  "project_id": "proj_abc123"
}
```

You must first create a project (or discover existing ones) before creating tasks under it. See the [Projects API](https://docs.zrb.dev/v2/projects) reference.

**Response codes:**

| Scenario | v1 | v2 |
|----------|----|----|
| Valid request | 201 | 201 |
| Missing `project_id` | N/A (no such field) | 422 |
| Missing `title` | 400 | 400 |

---

### 6. List Response Format: Bare Array → Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope with `items`, `total`, and `next_cursor`.

**v1 (old):**
```json
GET /tasks
→
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**v2 (new):**
```json
GET /v2/tasks
→
{
  "items": [
    {"id": "dd1c2…", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "ee3f4…", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

Update client code that previously iterated directly over the response array. Access `response.items` for the list.

---

### 7. Pagination: Cursor-Based

v1 returned all results in a single response (no pagination). v2 uses cursor-based pagination with a default limit of 20 items per page.

**v2 — first page:**
```
GET /v2/tasks?limit=20
```

**v2 — subsequent page:**
```
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

The `next_cursor` value is `null` when there are no more pages. Switch to a paginated fetch loop instead of a single request.

---

## Summary: What Changed

| Area | v1 | v2 | Impact |
|------|----|----|--------|
| Auth header | `X-Auth-Token` | `Authorization: Bearer` | All clients |
| Endpoint path | `/tasks` | `/v2/tasks` | All clients |
| Task `id` type | integer | UUID string | Stored IDs, URL construction |
| Status field | `done` | `completed` | All reads/writes of this field |
| Create task body | `{title}` | `{title, project_id}` | Task creation flows |
| List response | bare array | `{items, total, next_cursor}` | List consumers |
| Pagination | none | cursor-based, default 20 | All list consumers |

---

## Migration Checklist

Run through these steps in order:

- [ ] **Generate a Bearer token.** Replace all `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] **Create projects.** Use the Projects API to set up projects and record their `project_id` values.
- [ ] **Update task creation.** Add `project_id` to all `POST /tasks` request bodies.
- [ ] **Update all field references.** Rename `done` to `completed` in requests, responses, and client-side models.
- [ ] **Update list response handling.** Unwrap the paginated envelope — access `response.items` instead of the raw array.
- [ ] **Implement cursor pagination.** Replace single-shot list fetches with a paginated loop using `cursor` and `limit`.
- [ ] **Replace integer IDs with UUIDs.** Re-fetch tasks to obtain their v2 UUIDs. Update any hardcoded or cached IDs. Replace integer type constraints with string type constraints.
- [ ] **Prepend `/v2/` to all endpoint paths.**
- [ ] **Test.** Run your integration against the v2 endpoints and verify Create, Read, Update, Delete, and List operations against your project.

---

## Upgrade Command

```
npm install @zrb/client@^2.0.0
```

If you use the REST API directly, no package upgrade is needed — just update your HTTP calls as described above. Consult the [v2 API Reference](https://docs.zrb.dev/v2) for additional details on new features and best practices.
