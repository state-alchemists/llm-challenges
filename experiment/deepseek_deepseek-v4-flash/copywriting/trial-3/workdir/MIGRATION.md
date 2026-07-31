# Zrb v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. Six changes to the Zrb Task API are breaking — if you are already using v1, every one of them can silently break a request, a parser, or stored data. This guide walks through each breaking change with before/after examples, then ends with a migration checklist and the upgrade command.

The intended audience is developers currently on v1. For the full reference, see `v1_spec.md` and `v2_spec.md`.

## Breaking Changes at a Glance

| # | Area | v1 | v2 |
|---|------|-----|-----|
| 1 | Endpoint paths | `/tasks` | `/v2/tasks` |
| 2 | Auth header | `X-Auth-Token: <api_key>` | `Authorization: Bearer <token>` |
| 3 | Task `id` | Integer (e.g. `42`) | UUID string (e.g. `"a1b2c3d4-…"`) |
| 4 | Completion field | `done` | `completed` |
| 5 | Create Task body | `{ "title": … }` | `{ "title": …, "project_id": … }` — `project_id` required |
| 6 | List responses | Bare array | Paginated envelope |

## 1. Endpoint Paths Now Include `/v2/`

All endpoints moved under the `/v2/` prefix. Unprefixed paths are no longer served.

**Before**

```http
GET /tasks
POST /tasks
PUT /tasks/42
```

**After**

```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Full endpoint map:

| Operation | v1 | v2 |
|-----------|-----|-----|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

Update base URLs, generated clients, and any hardcoded paths in a single pass.

## 2. Authentication Header Changed

The `X-Auth-Token` header is gone. v2 requires a Bearer token, and requests that still send `X-Auth-Token` are rejected with **HTTP 401**.

**Before**

```http
X-Auth-Token: <your_api_key>
```

**After**

```http
Authorization: Bearer <your_api_token>
```

Update every caller — SDKs, scripts, CI jobs, curl commands. Do not reuse the v1 header name in middleware or proxies; it is treated as an unknown header and authentication fails.

## 3. Task `id` Changed from Integer to UUID String

Task IDs are now UUID strings instead of integers. This affects response parsing, URL construction, and anything that stores or compares task IDs (databases, caches, logs).

**Before**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Any code that treats `id` as an integer — `parseInt`, numeric comparisons, integer columns — must switch to string handling. Endpoint paths use the UUID as-is:

**Before**

```http
GET /tasks/42
```

**After**

```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## 4. `done` Renamed to `completed`

The completion flag is now `completed` in both request bodies and responses. The `done` field no longer exists in v2.

**Before**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After**

```json
{
  "title": "Updated title",
  "completed": true
}
```

Update request serializers and response models together — a client that still reads `done` will see it as `undefined`/`null` on every v2 task.

## 5. `project_id` Is Now Required When Creating Tasks

v2 introduces projects. `POST /v2/tasks` requires `project_id`; omitting it returns **HTTP 422**. The created task also includes `project_id`.

**Before**

```json
{
  "title": "New task title"
}
```

**After**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Create your projects before you can create tasks, and thread the `project_id` through create flows. Update (`PUT`) remains all-fields-optional.

## 6. List Responses Are Now Paginated Envelopes

`GET /v2/tasks` no longer returns a bare array. Every list endpoint returns an envelope with `items`, `total`, and a `next_cursor` for fetching the next page.

**Before**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "2024-01-15T10:30:00Z"},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "2024-01-15T10:30:00Z"}
]
```

**After**

```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Iterate by passing the cursor back:

```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

- `cursor` — optional pagination cursor
- `limit` — max results per page, default `20`

Any code that iterates the list response as an array must read `.items` instead, and loops must follow `next_cursor` until no further page is returned.

## What Didn't Change

- `title` field
- `created_at` format (ISO 8601)
- `GET /v2/tasks/{id}` returns `404` when the task does not exist
- `DELETE /v2/tasks/{id}` returns `204 No Content`
- `POST /v2/tasks` returns `201` with the created task
- `PUT` semantics — all fields optional on update

## Migration Checklist

Work through these top to bottom:

1. **Audit.** Grep your codebase for every v1 surface: `X-Auth-Token`, `/tasks` paths, the `done` field, integer task IDs, and bare-array list parsing.
2. **Upgrade Zrb** to v2 (see [Upgrade Command](#upgrade-command) below).
3. **Switch authentication.** Replace `X-Auth-Token: <api_key>` with `Authorization: Bearer <token>` in all clients, SDKs, scripts, and CI jobs.
4. **Prefix all paths with `/v2/`.** Update base URLs and any hardcoded endpoint strings (see the endpoint map in change 1).
5. **Migrate stored IDs.** Convert persisted task IDs (caches, databases, logs) from integers to UUID strings; re-fetch lists from the API to pick up v2 IDs.
6. **Rename `done` → `completed`** in request serializers and response models.
7. **Create projects and add `project_id`** to every create-task call; handle the `422` response for missing `project_id` as a validation error.
8. **Rewrite list handling** for the paginated envelope — read `items`, iterate on `next_cursor`, and honor `limit`.
9. **Update type definitions, mocks, and tests** to the v2 Task shape (`id` string, `completed`, `project_id`).
10. **Run a smoke test** end to end: create → list → get → update → delete, plus the error paths (401 with the old auth header, 422 without `project_id`).
11. **Roll out**, then watch for residual v1 patterns in logs (401s and 404s usually point at a missed caller).

## Upgrade Command

```bash
pip install --upgrade zrb
```

If you installed Zrb with pipx instead:

```bash
pipx upgrade zrb
```

After upgrading, re-run step 10 of the checklist against the v2 API to confirm the migration.
