# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, stricter authentication, and several breaking changes to align the API with REST best practices. This guide covers every difference you need to address.

---

## Breaking Changes at a Glance

| Area | v1 | v2 |
|------|----|----|
| Base path | `/tasks` | `/v2/tasks` |
| Auth header | `X-Auth-Token` | `Authorization: Bearer` |
| Task `id` type | Integer | UUID string |
| Task field `done` | `done` | `completed` |
| Task creation | `title` only | `title` + `project_id` (required) |
| List response | Bare array | Paginated envelope (`items`, `total`, `next_cursor`) |
| Pagination | None | Cursor-based (`?cursor=`, `?limit=`) |

---

## 1. Endpoint Prefix

All v2 endpoints are prefixed with `/v2/`.

```diff
- GET /tasks
+ GET /v2/tasks

- POST /tasks
+ POST /v2/tasks

- PUT /tasks/{id}
+ PUT /v2/tasks/{id}

- DELETE /tasks/{id}
+ DELETE /v2/tasks/{id}
```

Update your base URL or path builder to include `/v2` before the resource.

---

## 2. Authentication

The header format changed from a custom `X-Auth-Token` to the standard `Authorization: Bearer` scheme.

**v1:**
```
X-Auth-Token: sk_live_abc123
```

**v2:**
```
Authorization: Bearer sk_live_abc123
```

Requests using the old header will receive HTTP 401. Update your client's auth configuration — this is typically a one-line change in the request builder.

---

## 3. Task ID Is Now a UUID

The `id` field changed from an auto-incrementing integer to a UUID string (v4).

**v1 (integer):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**v2 (UUID string):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

**Impact:**
- Replace any integer type hints or schemas with `string` (format: UUID).
- Local databases or caches keyed on integer `id` need a migration.
- Hard-coded task IDs in test fixtures, seed data, or scripts must be regenerated.
- The `GET /v2/tasks/{id}` endpoint now accepts UUIDs only — integer IDs from v1 will not resolve.

---

## 4. `done` Renamed to `completed`

The boolean completion field is now `completed`.

| v1 | v2 |
|----|----|
| `"done": true` | `"completed": true` |
| `"done": false` | `"completed": false` |

**v1 request:**
```json
PUT /tasks/42
{
  "title": "Write tests",
  "done": true
}
```

**v2 request:**
```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{
  "title": "Write tests",
  "completed": true
}
```

Search your codebase for all references to the `done` field — API payloads, response parsers, type definitions, and database columns — and rename them to `completed`.

---

## 5. `project_id` Is Now Required on Create

Every task must belong to a project. The `project_id` field is required when creating a task.

**v1:**
```json
POST /tasks
{
  "title": "New task title"
}
```

**v2:**
```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Omitting `project_id` returns HTTP 422 with a validation error. You must either:
- Assign tasks to an existing project (recommended), or
- Create a default project (e.g., "General") and map uncategorised tasks to it.

The response body for created tasks also includes `project_id`.

---

## 6. List Responses Use a Paginated Envelope

All list endpoints now return a paginated envelope instead of a bare array.

**v1 (bare array):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**v2 (paginated envelope):**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false},
    {"id": "e5f6a7b8-...", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**v2 query params:**
- `?cursor=<next_cursor>` — fetch the next page.
- `?limit=<number>` — results per page (default 20).

**Migration tasks:**
- Update response parsers to read from `response.items` instead of the root array.
- Handle pagination: check for a non-null `next_cursor` and loop to fetch subsequent pages.
- Remove any offset/limit logic you may have built on v1 — v2 uses cursor-based pagination only.
- You can now use `total` for display purposes (e.g., "Showing 1–20 of 42 results").

---

## Step-by-Step Migration Checklist

- [ ] **Update endpoint URLs** — Replace `/tasks` with `/v2/tasks` in all API calls.
- [ ] **Replace auth header** — Change `X-Auth-Token: <key>` to `Authorization: Bearer <key>`.
- [ ] **Migrate task IDs** — Update any stored integer IDs to UUIDs. Re-seed test data. Update type definitions and schemas from `int`/`number` to `string`.
- [ ] **Rename `done` to `completed`** — Update all request payloads, response parsers, type definitions, and local data stores.
- [ ] **Provide a `project_id`** — Add `project_id` to every `POST /v2/tasks` call. Create a default project if you don't have one yet.
- [ ] **Update list response handling** — Read `response.items` instead of the root array. Build pagination loops using `next_cursor`.
- [ ] **Test end-to-end** — Exercise each CRUD operation against v2 and verify responses match the new schemas.
- [ ] **Deprecate v1 clients** — Once all consumers are migrated, remove v1 base URLs and disable `X-Auth-Token` validation on the server.

---

## Upgrade Your Client

```bash
# Python (requests)
pip install --upgrade zrb-client

# Node.js
npm update @zrb/client

# Go
go get github.com/zrb/client@v2
```

If you are using the API directly without a client library, update your base URL to `https://api.zrb.dev/v2` and apply the header and schema changes documented above.
