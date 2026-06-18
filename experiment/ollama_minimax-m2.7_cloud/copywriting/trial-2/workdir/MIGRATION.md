# Zrb CLI v1 to v2 Migration Guide

v2 introduces projects, UUID-based IDs, and a new authentication scheme. All v1 endpoints are replaced; there is no backward compatibility mode.

**Audience:** developers already using v1. This guide assumes familiarity with REST APIs, JSON, and HTTP status codes.

---

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Completion field name | `done` | `completed` |
| 5 | Create requires `project_id` | not present | required string |
| 6 | List response shape | bare array `[{...}]` | paginated envelope `{items, total, next_cursor}` |

---

## 1 — Endpoint Prefix

All endpoints now carry the `/v2/` prefix. Requests to v1 paths receive `404`.

**Before (v1)**
```
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2)**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2 — Authentication Header

The custom `X-Auth-Token` header is replaced by the standard `Authorization: Bearer` scheme. Requests carrying `X-Auth-Token` will be rejected with `401`.

**Before (v1)**
```http
X-Auth-Token: your_api_key_here
```

**After (v2)**
```http
Authorization: Bearer your_api_token_here
```

---

## 3 — Task ID Type

Task IDs changed from auto-incrementing integers to UUID strings. Code that treats `id` as a number will break.

**Before (v1) — `id` is an integer**
```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z" }
```

**After (v2) — `id` is a UUID**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z" }
```

Update any code that serialises or passes `id` as an integer (e.g., URL paths, database foreign keys, state objects).

---

## 4 — Completion Field Renamed

The `done` boolean is renamed to `completed`. The meaning is identical.

**Before (v1)**
```json
{ "id": 1, "title": "Buy milk", "done": true, "created_at": "..." }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-...", "title": "Buy milk", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
```

Replace all references to `task.done` with `task.completed` in client code and storage schemas.

---

## 5 — `project_id` Required on Create

Task creation now requires a `project_id`. Omitting it returns `422 Unprocessable Entity`.

**Before (v1) — `POST /tasks` request body**
```json
{ "title": "New task title" }
```

**After (v2) — `POST /v2/tasks` request body**
```json
{ "title": "New task title", "project_id": "proj_abc123" }
```

Existing integrations must supply a valid `project_id` for every create call. If you do not already use projects, create one first via your project management surface before migrating task creation.

---

## 6 — List Response Envelope

`GET /v2/tasks` returns a paginated envelope instead of a bare array. Iteration logic that expects `Array.isArray` or similar will need updating.

**Before (v1) — bare array**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2) — paginated envelope**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To page forward, send `?cursor=<next_cursor>` on the next request. The `limit` query param controls page size (default 20).

---

## Migration Checklist

Run through each step in order. Mark each item done as you verify it.

- [ ] **Update base URL** — prepend `/v2` to every endpoint path.
- [ ] **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer`.
- [ ] **Replace `id` type** — change task ID variables from `int` to `string` / UUID. Update URL construction, database columns, and serialized state.
- [ ] **Rename `done` → `completed`** — find/replace in client code, templates, and storage.
- [ ] **Add `project_id` to create** — fetch or provision a `project_id` before enabling v2 create calls. Handle the new `422` response.
- [ ] **Update list handling** — change array-iteration code to read `response.items`, `response.total`, and `response.next_cursor`. Implement cursor-based pagination if you support full list traversal.
- [ ] **Update tests** — point test fixtures and mocks at v2 response shapes.
- [ ] **Deploy and smoke-test** — hit each endpoint manually or via your integration test suite and confirm `200`/`201`/`204` as appropriate.

---

## Upgrade Command

Once your codebase is updated:

```bash
pip install zrb --upgrade
```

Verify the installed version:

```bash
zrb --version
```
