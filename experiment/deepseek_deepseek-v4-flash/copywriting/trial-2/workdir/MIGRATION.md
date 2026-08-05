# Zrb Task API v1 → v2 Migration Guide

This guide covers every breaking change between the Zrb Task API v1 and v2. Migration is mechanical but not automatic: URLs, auth headers, ID types, and field names all change, so client code must be updated deliberately before it can talk to v2.

v2 introduces projects, cursor-based pagination, and stricter authentication. The task lifecycle (create, read, update, delete) and the `title`/`created_at` fields are unchanged. Everything else on the wire is different.

## Breaking changes at a glance

| Area | v1 | v2 |
|---|---|---|
| Endpoint prefix | `/tasks` | `/v2/tasks` |
| Authentication | `X-Auth-Token` | `Authorization: Bearer` |
| Task `id` type | integer | UUID string |
| Completion flag | `done` | `completed` |
| Task creation | title only | `project_id` required |
| List responses | bare array | paginated envelope |

## 1. All endpoints move under `/v2/`

Every endpoint is now prefixed with `/v2/`. Old paths return 404, so update base URLs and any hardcoded routes.

**Before (v1):**

```bash
curl -H "X-Auth-Token: $API_KEY" https://api.zrb.example/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer $API_TOKEN" https://api.zrb.example/v2/tasks
```

## 2. Authentication: Bearer tokens replace `X-Auth-Token`

The auth header changed from `X-Auth-Token` to `Authorization: Bearer <token>`. Requests that still send `X-Auth-Token` receive HTTP 401. Swap every client, SDK wrapper, and scheduled job in the same release — this header is all-or-nothing.

**Before (v1):**

```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.example/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.example/v2/tasks
```

## 3. Task IDs become UUID strings

`id` changes from an integer to a UUID string such as `a1b2c3d4-e5f6-7890-abcd-ef1234567890`. Treat IDs as opaque strings: stop numeric parsing, comparisons, and increments; migrate persisted IDs and regenerate caches.

**Before (v1):**

```json
{"id": 42, "title": "Write tests", "done": false}
```

**After (v2):**

```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123"}
```

## 4. `done` is renamed to `completed`

The completion flag is now `completed` in requests and responses. Sending `done` in `PUT /v2/tasks/{id}` silently fails to update the flag.

**Before (v1):**

```json
{"title": "Updated title", "done": true}
```

**After (v2):**

```json
{"title": "Updated title", "completed": true}
```

## 5. Task creation requires `project_id`

v2 introduces projects and every task must belong to one. `POST /v2/tasks` requires `project_id` in the body; omitting it returns HTTP 422. Plan the project mapping for existing tasks before you switch creation flows.

**Before (v1):**

```bash
curl -X POST https://api.zrb.example/tasks \
  -H "X-Auth-Token: $API_KEY" \
  -d '{"title": "New task title"}'
```

**After (v2):**

```bash
curl -X POST https://api.zrb.example/v2/tasks \
  -H "Authorization: Bearer $API_TOKEN" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

## 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns `{items, total, next_cursor}`; fetch more pages with `?cursor=<next_cursor>` and cap pages with `limit` (default 20). Code that indexes the response as an array (`data[0]`) must read `items` instead.

**Before (v1):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**After (v2):**

```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123"}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Unchanged in v2

- `title` and `created_at` keep names and formats.
- `GET /v2/tasks/{id}` returns a single task or 404.
- `PUT /v2/tasks/{id}` keeps optional fields; `DELETE /v2/tasks/{id}` still returns 204.
- Create and update responses use the v2 task object.

## Migration checklist

1. Map each of the six breaking changes to the client code that touches it.
2. Update the base URL and every endpoint to the `/v2/` prefix.
3. Replace `X-Auth-Token` keys with Bearer tokens in all auth headers.
4. Change `id` handling from integer to UUID string in types, caches, and persisted data.
5. Rename `done` to `completed` in every request and response parser.
6. Add `project_id` to all creation calls and backfill project membership for existing tasks.
7. Switch list handling to the paginated envelope and iterate with `cursor`.
8. Run your test suite against v2, then ship all client changes in one coordinated release.

## Upgrade to v2

```bash
pip install --upgrade zrb
```
