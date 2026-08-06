# Zrb v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. Six breaking changes affect every v1 client. This guide walks through each one with before/after examples, then gives a step-by-step migration checklist.

## What Changed at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Task `done` field | `done` | `completed` |
| 5 | Task creation | `title` only | `title` + `project_id` (required) |
| 6 | List responses | bare array | paginated envelope |

---

## Breaking Changes

### 1. All Endpoints Are Prefixed with `/v2/`

Every endpoint moves under `/v2`. Requests to the v1 paths are no longer served.

**Before (v1):**

```http
GET https://api.zrb.dev/tasks
POST https://api.zrb.dev/tasks
```

**After (v2):**

```http
GET https://api.zrb.dev/v2/tasks
POST https://api.zrb.dev/v2/tasks
```

Update your base URL once and derive all paths from it.

### 2. Authentication: `X-Auth-Token` → Bearer Token

The header and credential type both change. v1 API keys are no longer valid.

**Before (v1):**

```http
X-Auth-Token: <your_api_key>
```

**After (v2):**

```http
Authorization: Bearer <your_api_token>
```

Requests sent with `X-Auth-Token` receive HTTP 401. Issue a v2 token — the v1 API key does not work as a Bearer token.

### 3. Task `id` Is Now a UUID String

IDs were auto-assigned integers; they are now UUID strings. This affects path parameters, storage types, and anything that relied on numeric ordering.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

**Before (v1):**

```http
GET /tasks/42
```

**After (v2):**

```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Store IDs as strings. Do not sort, increment, or range-filter on `id` — use `created_at` if you need chronological ordering.

### 4. `done` Is Renamed to `completed`

The boolean field is renamed everywhere: task objects in responses and both create and update request bodies.

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

`done` no longer exists as a field name in v2. Update deserializers, serializers, and any code that reads `task.done` or writes `"done"`.

### 5. `project_id` Is Required When Creating Tasks

Tasks now belong to a project. Creation without a `project_id` fails with HTTP 422.

**Before (v1):**

```http
POST /tasks
```

```json
{
  "title": "New task title"
}
```

**After (v2):**

```http
POST /v2/tasks
```

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Obtain the `project_id` from the project's API representation before creating tasks, and treat it as a mandatory field in your create flow.

### 6. List Responses Are Paginated Envelopes

`GET /v2/tasks` no longer returns a bare array. All list endpoints return an envelope with `items`, `total`, and `next_cursor`.

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
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false},
    {"id": "e5f67890-...", "title": "Ship v2", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Page through results by passing the returned cursor:

```http
GET /v2/tasks?limit=20&cursor=cursor_xyz
```

`limit` defaults to 20. Keep requesting while `next_cursor` is present; a null or absent `next_cursor` means the last page. Iterate over `items`, never the envelope itself.

---

## Migration Checklist

1. **Get a v2 token.** Issue a Bearer token and store it in your credential manager.
2. **Update the base URL** to include the `/v2/` prefix, so all request paths derive from it.
3. **Replace the auth header.** Swap `X-Auth-Token: <key>` for `Authorization: Bearer <token>` in your client and any shared request builders.
4. **Update the task model.** Change `id` to a string/UUID type and rename `done` to `completed` in deserializers, serializers, and database mappings.
5. **Add `project_id` to create flows.** Fetch the target project ID and include it in every `POST /v2/tasks` body.
6. **Update update flows.** Ensure `PUT /v2/tasks/{id}` bodies use `completed`, not `done`.
7. **Handle the list envelope.** Unwrap `items` in list consumers and add a cursor loop that follows `next_cursor` until it is null.
8. **Grep for v1 leftovers.** Search your codebase for `X-Auth-Token`, `"done"`, `/tasks` (without `/v2`), and integer-typed task IDs; fix every hit.
9. **Re-run integration tests.** Verify success paths, and confirm the new failure modes: `401` for old auth headers and `422` for missing `project_id`.
10. **Deploy and monitor.** Ship behind a feature flag or during a maintenance window so you can roll back if a client still sends v1 traffic.

## Upgrading

```bash
zrb upgrade
```

Run the upgrade, then work through the checklist above before pointing any client at v2.
