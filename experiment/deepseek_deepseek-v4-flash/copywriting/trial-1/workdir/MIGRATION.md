# Zrb v2 Migration Guide

Zrb v2 introduces projects, paginated list responses, and stricter authentication. It also changes several v1 conventions that existing clients rely on — endpoint paths, the auth header, and core task fields. This guide walks through every breaking change with before/after examples, then ends with a migration checklist and the upgrade command.

If you use the v1 API directly, plan to update your client code in one pass: v1 requests using the old auth header will be rejected with HTTP 401, and the remaining changes are spread across paths, payloads, and response shapes.

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | All endpoints prefixed with `/v2/` | Every URL changes |
| 2 | Auth header changed from `X-Auth-Token` to `Authorization: Bearer` | Old header rejected with 401 |
| 3 | Task `id` is now a UUID string, not an integer | Parsers and stored IDs must change |
| 4 | Task field `done` renamed to `completed` | Reads and writes change |
| 5 | `project_id` is required when creating a task | Creates without it fail with 422 |
| 6 | List endpoints return a paginated envelope | Response shape and iteration change |

---

## Breaking Change 1: All endpoints moved under `/v2/`

Every endpoint is now prefixed with `/v2/`. The base URL is unchanged; only the path is different.

**Before (v1):**

```bash
curl -X GET \
  -H "X-Auth-Token: <your_api_key>" \
  https://YOUR_BASE_URL/tasks
```

**After (v2):**

```bash
curl -X GET \
  -H "Authorization: Bearer <your_api_token>" \
  https://YOUR_BASE_URL/v2/tasks
```

Applies to every endpoint:

| Operation | v1 | v2 |
|-----------|----|----|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

---

## Breaking Change 2: Authentication now uses Bearer tokens

The `X-Auth-Token` header is gone. Requests must use an `Authorization` header with a Bearer token. Requests sent with the old header receive **HTTP 401 Unauthorized**.

**Before (v1):**

```bash
curl -X GET \
  -H "X-Auth-Token: <your_api_key>" \
  https://YOUR_BASE_URL/tasks
```

**After (v2):**

```bash
curl -X GET \
  -H "Authorization: Bearer <your_api_token>" \
  https://YOUR_BASE_URL/v2/tasks
```

Update every request builder, client wrapper, and hardcoded header you ship. If you rotate tokens during the migration, regenerate credentials after cutting over to the new header.

---

## Breaking Change 3: Task `id` is now a UUID string

Task IDs changed from auto-assigned integers to UUID strings. Code that treats `id` as a number — parsing it, incrementing it, or storing it in an integer column — will break.

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

Treat `id` as an opaque string everywhere: in responses, in URL paths (`GET /v2/tasks/{id}`), and in your data model. Do not assume any numeric ordering — UUIDs are not sequential.

---

## Breaking Change 4: `done` is now `completed`

The boolean task field `done` was renamed to `completed`. This affects both task objects returned by the API and the request bodies you send.

**Before (v1) — reading a task:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — reading a task:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Before (v1) — updating a task:**

```bash
curl -X PUT \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated title", "done": true}' \
  https://YOUR_BASE_URL/tasks/42
```

**After (v2) — updating a task:**

```bash
curl -X PUT \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated title", "completed": true}' \
  https://YOUR_BASE_URL/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Update field mappings on both the read and the write side. `PUT` fields remain optional.

---

## Breaking Change 5: `project_id` is required when creating a task

Task creation now requires a `project_id`. The field is new in v2 and has no v1 equivalent — omitting it returns **HTTP 422 Unprocessable Entity**.

**Before (v1):**

```bash
curl -X POST \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}' \
  https://YOUR_BASE_URL/tasks
```

**After (v2):**

```bash
curl -X POST \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}' \
  https://YOUR_BASE_URL/v2/tasks
```

Every create path must supply a valid `project_id`. Callers that previously created tasks with only a title will start failing with 422 — decide up front where the project ID comes from in each flow.

---

## Breaking Change 6: List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`. Page through results with the `cursor` and `limit` query parameters (`limit` defaults to 20).

**Before (v1):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "2024-01-15T10:30:00Z"},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "2024-01-15T10:31:00Z"}
]
```

**After (v2):**

```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"},
    {"id": "f5e4d3c2-b1a0-9876-fedc-ba9876543210", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "2024-01-15T10:31:00Z"}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**After (v2) — fetching the next page:**

```bash
curl -X GET \
  -H "Authorization: Bearer <your_api_token>" \
  "https://YOUR_BASE_URL/v2/tasks?limit=20&cursor=cursor_xyz"
```

Read `items` instead of treating the response body as the array itself. Iterate by passing `?cursor=<next_cursor>` until the response no longer includes a `next_cursor`. Use `total` for counts and `limit` to control page size.

---

## What Did Not Change

The following v1 behavior is preserved in v2:

- `title` — string field, unchanged
- `created_at` — ISO 8601 timestamp, unchanged
- `GET /v2/tasks/{id}` returns HTTP 404 for a missing task
- `POST /v2/tasks` returns HTTP 201 with the created task
- `PUT /v2/tasks/{id}` accepts optional fields
- `DELETE /v2/tasks/{id}` returns HTTP 204 No Content

---

## Migration Checklist

Work through these in order. Step 1 is about finding every place v1 leaks into your code before you change anything.

1. **Inventory v1 usage.** Grep your codebase for `X-Auth-Token`, `/tasks`, `"done"`, and response shapes that treat list results as arrays. This is your migration surface.
2. **Switch authentication.** Replace the `X-Auth-Token` header with `Authorization: Bearer <token>` in every request. Confirm no code path still sends the old header — it now returns 401.
3. **Prefix endpoints with `/v2/`.** Update all base paths: `GET /tasks` → `GET /v2/tasks`, `POST /tasks` → `POST /v2/tasks`, and so on.
4. **Change task ID handling.** Update models, parsers, and storage to treat `id` as a UUID string. Drop any integer assumptions (parsing, arithmetic, sequential ordering).
5. **Rename `done` → `completed`.** Update response field mapping and request bodies. Remember this applies to reads and writes, including `PUT /v2/tasks/{id}`.
6. **Add `project_id` to task creation.** Determine the source of `project_id` for each create flow and include it in `POST /v2/tasks` bodies. Expect 422 if it is missing.
7. **Update list handling.** Read `items` from the envelope, use `total` for counts, and iterate pages with `cursor`/`limit` (default page size 20). Remove any code that assumes the response body is the array.
8. **Test against v2.** Verify every endpoint with the new auth header: 200/201 responses, 404 for missing tasks, 422 for a missing `project_id`, and pagination across multiple pages.
9. **Deploy and monitor.** Roll out the updated client, then watch for 401 (old auth), 422 (missing `project_id`), and empty `items` (list code still reading the old shape).

---

## Upgrade

Install the v2 release of the Zrb CLI:

```bash
pip install --upgrade zrb
```
