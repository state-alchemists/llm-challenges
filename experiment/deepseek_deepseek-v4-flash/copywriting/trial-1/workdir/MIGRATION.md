# Zrb Task API — v1 to v2 Migration Guide

v2 of the Zrb Task API introduces projects, cursor-based pagination, and stricter authentication. Every existing v1 endpoint, auth mechanism, and task data type has changed. This guide covers every breaking change with before/after examples so you can migrate your integrations with minimal friction.

If you are starting a new integration, skip this guide and use the [v2 API reference](./v2_spec.md) directly.

---

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoint prefix `/v2/` added | All URLs change |
| 2 | Auth header: `X-Auth-Token` → `Authorization: Bearer` | Every request must be re-signed |
| 3 | Task `id` type: integer → UUID string | ID-dependent logic must be updated |
| 4 | Task field: `done` → `completed` | All read and write code must use the new name |
| 5 | Task creation now requires `project_id` | Create-task calls without it will receive HTTP 422 |
| 6 | List response: bare array → paginated envelope | Consumers must unwrap `items` and handle cursors |

---

## 1. Endpoint URL Prefix

**Change:** All endpoints are now prefixed with `/v2/`. The old paths return 404.

**Before (v1):**

```
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

**What to do:** Update the base URL in your client configuration. If you use a client library, bump the path prefix.

---

## 2. Authentication Header

**Change:** The API key was sent via the `X-Auth-Token` header. v2 requires a Bearer token in the `Authorization` header. Requests using the old header receive HTTP 401.

**Before (v1):**

```http
X-Auth-Token: <your_api_key>
```

**After (v2):**

```http
Authorization: Bearer <your_api_token>
```

**What to do:** Replace the `X-Auth-Token` header with `Authorization: Bearer`. The token itself is different from the v1 API key — generate a new token via your account dashboard.

---

## 3. Task ID Type Changed (Integer → UUID String)

**Change:** Task identifiers are now UUID strings instead of auto-incrementing integers. Existing tasks retain their identity; the UUID is the stable identifier across the migration.

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

**What to do:**
- Update any code that assumes `id` is an integer (DB schemas, type annotations, URL construction).
- Reference tasks by their UUID string in all endpoints: `GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890`.

---

## 4. Task Field Renamed: `done` → `completed`

**Change:** The boolean field indicating completion status has been renamed from `done` to `completed`. The old field is not present in v2 responses, and the v2 PUT endpoint ignores it.

**Before (v1) — reading a task:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": true
}
```

**After (v2) — reading a task:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": true,
  "project_id": "proj_abc123"
}
```

**Before (v1) — updating a task:**

```http
PUT /tasks/42
Content-Type: application/json

{
  "done": true
}
```

**After (v2) — updating a task:**

```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Content-Type: application/json
Authorization: Bearer <token>

{
  "completed": true
}
```

**What to do:** Rename all references to `done` to `completed` in your request bodies and response parsing code. For database-local state, consider a migration that renames the column to keep the codebase consistent.

---

## 5. Task Creation Now Requires `project_id`

**Change:** Creating a task now requires a `project_id` field in the request body. Omitting it returns HTTP 422 with a validation error. The v1 endpoint accepted a bare `title` with no project affiliation.

**Before (v1):**

```http
POST /tasks
Content-Type: application/json

{
  "title": "New task"
}
```

**Response (201):**

```json
{
  "id": 43,
  "title": "New task",
  "done": false,
  "created_at": "2024-01-15T11:00:00Z"
}
```

**After (v2):**

```http
POST /v2/tasks
Content-Type: application/json
Authorization: Bearer <token>

{
  "title": "New task",
  "project_id": "proj_abc123"
}
```

**Response (201):**

```json
{
  "id": "a1b2c3d4-...",
  "title": "New task",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T11:00:00Z"
}
```

**What to do:**
- Obtain a project ID from the Zrb dashboard before migrating task-creation logic.
- Add `project_id` to every `POST /v2/tasks` request body.
- Handle HTTP 422 responses gracefully during the transition window (e.g., surface a clear error message pointing to the missing field).

---

## 6. List Response Format (Bare Array → Paginated Envelope)

**Change:** The list-tasks endpoint no longer returns a bare JSON array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`. Consumers that index directly into the response body will break.

**Before (v1):**

```http
GET /tasks
```

**Response:**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2):**

```http
GET /v2/tasks
Authorization: Bearer <token>
```

**Response:**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "e5f6g7h8-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 2,
  "next_cursor": null
}
```

**Cursor-based pagination:**

```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
Authorization: Bearer <token>
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cursor` | string | — | Opaque cursor from the previous response's `next_cursor` |
| `limit` | integer | 20 | Max items per page |

When `next_cursor` is `null`, there are no more pages.

**What to do:**
- Unwrap the response: access `.items` instead of treating the response as an array.
- Use `.next_cursor` in a loop to fetch subsequent pages instead of page-number-based navigation.
- Optionally pass `limit` to control page size.

---

## Migration Checklist

Use this step-by-step checklist to migrate each integration. Tick items off as you go.

- [ ] **Generate a Bearer token** for v2 (your v1 API key will not work).
- [ ] **Update the base URL** — add `/v2/` to all endpoint paths.
- [ ] **Replace the auth header** — change `X-Auth-Token: <key>` to `Authorization: Bearer <token>`.
- [ ] **Update task ID handling** — change integer IDs to UUID strings in URL construction, caching, and local storage.
- [ ] **Rename `done` to `completed`** in all request bodies and response parsers.
- [ ] **Add `project_id` to task creation** — identify the correct project(s) and include the field in every `POST /v2/tasks`.
- [ ] **Unwrap list responses** — access `.items` instead of indexing the response body directly.
- [ ] **Replace page-number pagination** with cursor-based logic using `.next_cursor`.
- [ ] **Update local database schemas** to match the v2 data types (UUID PKs, `completed` column, nullable `project_id`).
- [ ] **Test against the v2 API** in a staging environment before promoting to production.

---

## Upgrade Command

Once your code is updated, upgrade your client library or regenerate the API bindings:

```bash
pip install --upgrade zrb-client
```

If you use the Docker image:

```bash
docker pull zrb/client:v2
```

The v1 API will be available for a 90-day deprecation window starting from the v2 release date. After that, v1 endpoints will return HTTP 410 Gone.
