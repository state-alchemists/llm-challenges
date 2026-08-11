# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers **every breaking change** and shows exactly what to update in your code.

If you're currently on v1, the six changes below are required. Non-migrating requests will receive `401` or `422` errors.

---

## 1. All endpoints are now prefixed with `/v2/`

Every v1 endpoint path has moved under the `/v2/` prefix. The old paths are no longer served.

**Before (v1):**

```bash
GET  /tasks
GET  /tasks/42
POST /tasks
PUT  /tasks/42
DELETE /tasks/42
```

**After (v2):**

```bash
GET  /v2/tasks
GET  /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT  /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**What to do:** Update your base URL or route definitions. If you use a client with a configurable base path, change it from `/` to `/v2`. If you hardcode paths, find-and-replace `/tasks` → `/v2/tasks` (watch out for false matches in non-API strings).

---

## 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

v2 no longer accepts the `X-Auth-Token` header. Requests using it receive **HTTP 401 Unauthorized**.

**Before (v1):**

```bash
curl -H "X-Auth-Token: your_api_key" https://api.zrb.dev/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer your_api_key" https://api.zrb.dev/v2/tasks
```

**What to do:** Replace any `X-Auth-Token` header logic with a standard `Authorization: Bearer <token>` header. Most HTTP clients have built-in bearer-token support — use it rather than setting a custom header.

---

## 3. Task `id` changed from integer to UUID string

Task identifiers are now UUIDs, not auto-incrementing integers. Any code that stores, compares, or constructs URLs with task IDs must be updated.

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

- Change any database columns, struct fields, or type annotations from `int` / `integer` to `string` / `varchar`.
- Remove any integer-specific logic (ordering by `id`, arithmetic on `id`, validation that `id` is numeric).
- URL-template code that builds paths like `/tasks/${id}` still works — the ID is just a string now, not a number.

---

## 4. Task field `done` renamed to `completed`

The boolean field that marks a task as finished has been renamed.

**Before (v1):**

```json
{
  "title": "Ship v2",
  "done": true
}
```

**After (v2):**

```json
{
  "title": "Ship v2",
  "completed": true
}
```

**What to do:** Search your codebase for `"done"` (including in JSON parsing, serializers, conditionals, and query filters) and replace it with `"completed"`. Be careful not to change unrelated uses of "done" (e.g., progress bars, UI labels).

---

## 5. Task creation now requires `project_id`

v2 introduces projects. Every task must belong to one, so the `project_id` field is **required** on creation. Omitting it returns **HTTP 422 Unprocessable Entity**.

**Before (v1):**

```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**

```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

**What to do:**

- Ensure every `POST /v2/tasks` request includes `"project_id"`.
- If you have code that creates tasks without a project context, add a project selector or default to an existing project ID.
- Update your request schemas, validators, and tests to require this field.

---

## 6. List endpoints return a paginated envelope instead of a bare array

v1 returned a bare JSON array. v2 wraps results in a paginated envelope with cursor-based pagination.

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
    {"id": "e5f67890-...", "title": "Ship v1", "completed": true, "project_id": "proj_xyz789", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Fetch the next page with `?cursor=<next_cursor>`. The `limit` query parameter controls page size (default 20).

**Before (v1):**

```bash
curl https://api.zrb.dev/tasks
```

**After (v2):**

```bash
# First page
curl https://api.zrb.dev/v2/tasks

# Next page
curl https://api.zrb.dev/v2/tasks?cursor=cursor_xyz

# Custom page size
curl https://api.zrb.dev/v2/tasks?limit=50
```

**What to do:**

- Update your response parsing: instead of treating the response body as an array, extract `response.items` as the task list.
- If you were iterating over all results, implement cursor-based pagination using `next_cursor`. When `next_cursor` is `null` or absent, you've reached the last page.
- Remove any offset-based pagination logic (e.g., `?page=2`) — v2 uses cursors only.

---

## Migration Checklist

Work through each item in order. Most changes are independent, but we recommend updating the URL prefix and auth header first since those affect every request.

- [ ] **Update base URL** — Add `/v2/` prefix to all API paths (or set your client's base URL to include `/v2`).
- [ ] **Switch auth header** — Replace `X-Auth-Token` with `Authorization: Bearer` on every request.
- [ ] **Change task `id` type** — Update schemas, database columns, and type definitions from integer to UUID string.
- [ ] **Rename `done` to `completed`** — Update all references in serialization, deserialization, conditionals, and filters.
- [ ] **Add `project_id` to task creation** — Ensure every `POST` request includes a valid `project_id`.
- [ ] **Adapt list response parsing** — Extract `items` from the paginated envelope; implement cursor-based pagination using `next_cursor`.
- [ ] **Test end-to-end** — Run your integration test suite against a v2 staging environment.

---

Upgrade now:

```bash
npm install zrb@2
```