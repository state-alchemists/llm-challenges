# Zrb v2 Migration Guide

This guide covers everything that changed between the v1 and v2 Zrb Task API and how to migrate your existing code. v2 introduces projects, paginated list responses, and stricter authentication. Every change below is breaking — v1 requests either fail outright (HTTP 401, 422, 404) or return data in a different shape. Plan to update your client in a single pass: v1 and v2 are **not** wire-compatible.

If you are already using v1, read the six breaking changes in order, apply the corresponding code changes, then work through the [migration checklist](#migration-checklist) before you [upgrade](#upgrade).

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every endpoint moved under the `/v2/` prefix. Requests to the old paths return `404`.

**Before**

```bash
curl -H "X-Auth-Token: your_api_key" https://api.zrb.example/tasks
```

**After**

```bash
curl -H "Authorization: Bearer your_api_token" https://api.zrb.example/v2/tasks
```

Affected endpoints:

| v1 | v2 |
|----|----|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

Update your client's base URL or path prefix once, and every endpoint call follows.

### 2. Authentication header changed

The `X-Auth-Token` header is replaced by a Bearer token in the `Authorization` header. Requests that still send `X-Auth-Token` receive `401`.

**Before**

```bash
curl -H "X-Auth-Token: your_api_key" https://api.zrb.example/v2/tasks
```

**After**

```bash
curl -H "Authorization: Bearer your_api_token" https://api.zrb.example/v2/tasks
```

If you centralize headers in one place (an HTTP client factory, a middleware, or an auth module), this is a one-line change. Otherwise, replace every occurrence of `X-Auth-Token: <your_api_key>` with `Authorization: Bearer <your_api_token>`, then confirm a v2 request no longer returns `401`.

### 3. Task `id` is now a UUID string instead of an integer

Task ids changed from auto-assigned integers to UUID strings. Code that treats ids as numbers — arithmetic, integer type annotations, database columns, or URL construction that interpolates the id — must treat ids as opaque strings.

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

Do not assume a format or parse the id; pass it through verbatim when calling `GET /v2/tasks/{id}`, `PUT /v2/tasks/{id}`, or `DELETE /v2/tasks/{id}`. Migrate any stored v1 integer ids (map them to the new UUIDs returned by `GET /v2/tasks`) before you delete v1 data.

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed` in both request bodies and responses. The old name is no longer accepted.

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

Update every request payload that sets the flag and every response parser that reads it. In strongly typed clients, rename the field in your models so deserialization does not silently drop `completed`.

### 5. Creating a task now requires `project_id`

`POST /v2/tasks` requires `project_id` in the request body. Omitting it returns `422`.

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

Fetch the list of valid project ids ahead of time (for example, via the projects endpoint or your organization's project directory) and include the id with every create call. Treat `422` as a signal that the `project_id` is missing or invalid, and handle it in your error path.

### 6. List endpoints return a paginated envelope instead of a bare array

List endpoints (e.g. `GET /v2/tasks`) no longer return a bare array. The response is now an envelope with `items`, `total`, and `next_cursor`. Pagination is controlled by the `cursor` and `limit` query parameters (`limit` defaults to 20).

**Before**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After**

```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Replace any code that iterates the response array directly — read `items` instead, and page through the full result set by passing `next_cursor` back as `?cursor=` until the API returns no further `next_cursor`:

```bash
curl "https://api.zrb.example/v2/tasks?cursor=cursor_xyz&limit=20"
```

Also note the default page size: if your code assumed an unbounded list, add an explicit `limit` and loop on the cursor, or you will only see the first 20 results.

## What Hasn't Changed

- `title` and `created_at` keep their names and types.
- `GET /v2/tasks/{id}` still returns a single task or `404`.
- `PUT /v2/tasks/{id}` still accepts an all-optional body and returns the updated task.
- `DELETE /v2/tasks/{id}` still returns `204 No Content`.
- `POST /v2/tasks` still returns the created task with `201`.

## Migration Checklist

Work through these steps in order:

1. **Prefix every endpoint with `/v2/`.** Update your base URL or path builder so all five endpoint calls hit the new paths.
2. **Switch to Bearer authentication.** Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>` everywhere; verify a v2 request no longer returns `401`.
3. **Treat task ids as UUID strings.** Update type annotations, comparisons, and storage; pass ids through verbatim in URL paths.
4. **Rename `done` to `completed`.** Update request payloads and response parsing, including any client-side models.
5. **Add `project_id` to every create call.** Resolve valid project ids before sending; handle `422` responses as missing/invalid `project_id`.
6. **Update list parsing for the envelope.** Read `items`, honor `total`, and loop on `next_cursor` with an explicit `limit` until the API returns no further cursor.
7. **Run your test suite against v2.** Verify the status-code contract end to end: `201` on create, `204` on delete, `404` on missing task, `401` on bad auth, `422` on missing `project_id`.

## Upgrade

```bash
pip install --upgrade zrb
```

If zrb was installed via pipx:

```bash
pipx upgrade zrb
```
