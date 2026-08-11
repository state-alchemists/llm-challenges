# Zrb Task API v2 Migration Guide

This guide walks experienced v1 users through the breaking changes in the Zrb Task API v2 release. Six changes require code updates: a new `/v2/` URL prefix, a new authentication header, UUID task IDs, the `done` → `completed` rename, a required `project_id`, and paginated list responses. Each change has a before/after example below, followed by a step-by-step migration checklist and the upgrade command.

> Your API host does not change — only the paths, headers, and payloads described below.

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Field rename | `done` | `completed` |
| 5 | Create requirement | `title` only | `title` + `project_id` |
| 6 | List response | bare array | paginated envelope |

## 1. Endpoint Prefix: `/v2/`

Every endpoint is now prefixed with `/v2/`. Update your base path or router configuration.

| Operation | v1 | v2 |
|---|---|---|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1)**

```bash
curl https://api.example.com/tasks
```

**After (v2)**

```bash
curl https://api.example.com/v2/tasks
```

## 2. Authentication: `X-Auth-Token` → Bearer Token

Replace the `X-Auth-Token` header with an `Authorization: Bearer` header.

**Before (v1)**

```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.example.com/tasks
```

**After (v2)**

```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.example.com/v2/tasks
```

Requests that still send `X-Auth-Token` are rejected with **HTTP 401**, even if the key is valid. Issue or rotate bearer tokens and update any stored credentials, SDK defaults, and CI secrets.

## 3. Task ID: Integer → UUID String

Task `id` values are now UUID strings instead of integers.

**Before (v1)**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2)**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Treat `id` as an opaque string: stop numeric parsing, auto-increment assumptions, and range comparisons. The same value goes into the `{id}` path segment for get, update, and delete:

**Before (v1)**

```bash
curl -X DELETE https://api.example.com/tasks/42
```

**After (v2)**

```bash
curl -X DELETE https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## 4. Field Rename: `done` → `completed`

The task boolean field `done` is renamed `completed` in both request bodies and responses.

**Before (v1)**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2)**

```json
{
  "title": "Updated title",
  "completed": true
}
```

Update your serializers, deserializers, and any code that reads `task.done` (or `task["done"]`) to use `completed`. The v2 API recognizes only `completed`; the v1 field name is no longer supported.

## 5. Create Task Now Requires `project_id`

Creating a task now requires `project_id` in addition to `title`. Omitting it returns **HTTP 422**.

**Before (v1)**

```bash
curl -X POST https://api.example.com/tasks \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2)**

```bash
curl -X POST https://api.example.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

Obtain a valid `project_id` before creating tasks — through the project list API or from your configuration — and plumb it through every create code path.

## 6. List Responses Are Paginated Envelopes

List endpoints no longer return a bare array. They return a paginated envelope.

**Before (v1)**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "2024-01-10T09:00:00Z"},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "2024-01-11T18:30:00Z"}
]
```

**After (v2)**

```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "created_at": "2024-01-10T09:00:00Z"},
    {"id": "e5f6a7b8-c9d0-1234-5678-9abcdef01234", "title": "Ship v1", "completed": true, "created_at": "2024-01-11T18:30:00Z"}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Changes to make in your client:

- Read the results from `items` instead of parsing the top-level array.
- Use `total` for the total number of matching tasks.
- Pass `next_cursor` as the `cursor` query parameter to fetch the next page; `limit` (default 20) controls page size.

**Before (v1)**

```bash
curl "https://api.example.com/tasks?limit=20"
```

**After (v2)**

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.example.com/v2/tasks?limit=20&cursor=cursor_xyz"
```

## Step-by-Step Migration Checklist

1. **Update every endpoint URL** to the `/v2/` prefix (list, get, create, update, delete).
2. **Switch authentication** from `X-Auth-Token` to `Authorization: Bearer <token>`; rotate keys/tokens and update SDK defaults and CI secrets.
3. **Treat task IDs as opaque UUID strings** — remove numeric parsing, update path interpolation, and adjust any stored ID columns or schemas.
4. **Rename `done` → `completed`** in request builders and everywhere responses are read.
5. **Supply `project_id` on every create** — fetch project IDs first, and treat HTTP 422 as a signal that a create payload is incomplete.
6. **Rewrite list handling** for the envelope — read `items`, honor `total`, and implement cursor pagination with `cursor`/`limit`.
7. **Update your tests** — add one test per change above and run them against a v2 environment.
8. **Coordinate rollout** with any shared client libraries, other teams, and stored API keys.

## Upgrade

Run the following to upgrade the Zrb CLI (or the equivalent command for your package manager):

```bash
pip install --upgrade zrb
```
