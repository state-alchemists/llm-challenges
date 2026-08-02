# Zrb CLI v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. This guide walks experienced v1 developers through every breaking change so you can upgrade your integrations with minimal downtime.

If you only need the short version, the table below lists all six breaking changes; each is detailed with before/after examples in the sections that follow.

| # | Breaking change | v1 | v2 |
|---|-----------------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Field rename | `done` | `completed` |
| 5 | Required field | `project_id` optional (absent) | `project_id` required on create |
| 6 | List response shape | bare array | paginated envelope |

---

## 1. All Endpoints Are Now Prefixed with `/v2/`

Every endpoint moved under the `/v2/` prefix. Requests to the old paths will not be found.

**Before (v1):**

```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header Changed

The `X-Auth-Token` header is gone. v2 uses a standard Bearer token in the `Authorization` header. Requests that still send `X-Auth-Token` receive HTTP 401.

**Before (v1):**

```http
X-Auth-Token: <your_api_key>
```

**After (v2):**

```http
Authorization: Bearer <your_api_token>
```

Update every client and any stored configuration that hardcodes the old header name.

---

## 3. Task `id` Changed from Integer to UUID String

Task identifiers are no longer sequential integers. They are now UUID strings, which means they cannot be incremented, predicted, or stored in integer columns as-is.

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

Treat `id` as an opaque string: store it as text, and never rely on ordering or arithmetic over it. The UUID is used in all task paths, including `GET /v2/tasks/{id}`.

---

## 4. Field `done` Renamed to `completed`

The boolean completion flag is now `completed`. The field no longer exists in v2: responses will never contain `done`, and requests that send it will not set completion state.

**Before (v1):**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**

```json
{
  "title": "Updated title",
  "completed": true
}
```

This applies to responses, create/update request bodies, and any serialization layers (e.g., ORM models or API client types) that map the field.

---

## 5. Task Creation Now Requires `project_id`

New tasks must belong to a project. `project_id` is required on `POST`; omitting it returns HTTP 422. The update endpoint is otherwise unchanged apart from the path prefix and field rename — `title` and `completed` remain optional on `PUT`.

**Before (v1):**

```http
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2):**

```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

`project_id` is a string (e.g., `proj_abc123`), not a UUID. You must create or identify a project before creating tasks, and the value is required on every create call.

---

## 6. List Endpoints Return a Paginated Envelope

List responses are no longer bare arrays. v2 returns an envelope with `items`, `total`, and a `next_cursor` for cursor-based pagination. Page through results by passing `?cursor=<next_cursor>`; the page size defaults to 20 and can be adjusted with `?limit=`.

**Before (v1):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f67890-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Fetching the next page (v2):**

```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

Iterate until `next_cursor` is empty or absent. Anything that consumed the old array directly — `response.json()`, list indexing, array iteration — must now read `response.items`.

---

## Migration Checklist

Work through these in order. Each step is verifiable on its own before you move on.

1. **Upgrade the CLI** — install v2 (command at the end of this guide).
2. **Update authentication** — replace `X-Auth-Token` with `Authorization: Bearer` in all clients, scripts, and stored configs. Confirm an old-header request now returns 401.
3. **Reword all endpoint paths** — prepend `/v2/` to every route in your codebase and any webhook/URL configuration.
4. **Create or resolve projects** — obtain a valid `project_id` (e.g., `proj_abc123`) and record it in your configuration.
5. **Rename the completion field** — change `done` to `completed` in request bodies, response parsing, and your data models.
6. **Switch `id` handling to strings** — change task ID columns/fields to text, and remove any integer arithmetic or ordering assumptions.
7. **Adapt list consumers** — unwrap the paginated envelope (`items` / `total` / `next_cursor`) and implement cursor-based paging instead of assuming a bare array.
8. **Add `project_id` to creates** — update every `POST /v2/tasks` call to include `project_id`, and handle the 422 response for validation errors.
9. **Regression-test the happy path** — create a task, list tasks across pages, update it with `completed`, fetch it by UUID, delete it.
10. **Check for leftover v1 usage** — grep your codebase for `X-Auth-Token`, `/tasks`, `"done"`, and array-style list handling; all should be gone.

## Upgrade

After upgrading, re-run your tests against the v2 API before deploying. To install v2:

```bash
pip install --upgrade zrb
```
