# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. These improvements come with **six breaking changes** that require code updates before switching. This guide walks through each one.

**Quick summary of breaking changes:**

1. All endpoints are now prefixed with `/v2/`
2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`
3. Task `id` type changed from integer to UUID string
4. Task field `done` renamed to `completed`
5. Task creation now requires `project_id`
6. List endpoints return a paginated envelope instead of a bare array

---

## 1. Endpoint URL Prefix

All endpoints now require the `/v2/` prefix. Requests to the old paths will receive `404`.

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

If your base URL is configurable, update it from `https://api.example.com` to `https://api.example.com/v2`. Otherwise, prepend `/v2` to every endpoint path in your code.

---

## 2. Authentication Header

v2 replaces the custom `X-Auth-Token` header with the standard `Authorization: Bearer` scheme. Requests using the old header will receive `HTTP 401 Unauthorized`.

**Before (v1):**

```http
GET /tasks
X-Auth-Token: your_api_key
```

**After (v2):**

```http
GET /v2/tasks
Authorization: Bearer your_api_token
```

Update your HTTP client to send the token as a Bearer credential instead of a custom header. If you use a shared HTTP client or interceptor, centralize this change there.

---

## 3. Task ID Type Change

Task IDs are now UUID strings instead of auto-incremented integers. Any code that parses, stores, or validates task IDs must be updated.

**Before (v1):**

```json
{
  "id": 42
}
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

Implications:

- **Database columns** storing task IDs must change from integer types to UUID or string types.
- **URL route parameters** that parse `id` as an integer must accept UUID strings instead.
- **Client-side models** that declare `id` as `number` or `int` must be updated to `string`.

---

## 4. Field Rename: `done` → `completed`

The boolean field `done` on the task object has been renamed to `completed`. The old name is no longer accepted in responses or in update request bodies.

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

**Updating a task's completion status (v1):**

```json
PUT /tasks/42

{
  "done": true
}
```

**Updating a task's completion status (v2):**

```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890

{
  "completed": true
}
```

Search your codebase for all references to the `done` field — including JSON deserialization, model definitions, conditionals, and test assertions — and replace them with `completed`.

---

## 5. Required `project_id` on Task Creation

Creating a task now requires a `project_id`. Omitting it returns `HTTP 422 Unprocessable Entity`.

**Before (v1):**

```json
POST /tasks

{
  "title": "New task title"
}
```

**After (v2):**

```json
POST /v2/tasks

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

You must update every `POST /tasks` call in your integration to include `"project_id"`. If you have not adopted projects yet, create a default project and use its ID as the `project_id` value.

---

## 6. Paginated List Response

List endpoints no longer return a bare array. They now return a paginated envelope containing `items`, `total`, and `next_cursor`.

**Before (v1):**

```json
GET /tasks

[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**

```json
GET /v2/tasks

{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f67890-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page:

```http
GET /v2/tasks?cursor=cursor_xyz
```

When `next_cursor` is `null` or absent, there are no more pages. You can optionally pass `?limit=<n>` to control page size (default 20).

**Client update:** any code that iterates over a raw JSON array from the list endpoint must instead read from the `items` key. If you need all results at once, implement a loop that follows `next_cursor` until it is exhausted.

---

## Migration Checklist

Work through these steps in order. Each step maps to one breaking change above.

- [ ] **1. Update endpoint URLs** — prepend `/v2` to all task endpoint paths (or update the base URL).
- [ ] **2. Update authentication** — replace `X-Auth-Token` header with `Authorization: Bearer` header in all API calls and shared HTTP clients.
- [ ] **3. Update ID handling** — change task ID storage, parsing, and validation from integer to UUID string. Update database columns, route parameters, and client models.
- [ ] **4. Rename `done` to `completed`** — update all model definitions, serializers, conditionals, and test assertions that reference the `done` field.
- [ ] **5. Add `project_id` to task creation** — include `project_id` in every `POST /v2/tasks` request body. Create a default project if you have not adopted projects yet.
- [ ] **6. Handle paginated responses** — update all list-endpoint consumers to read from the `items` key. Implement cursor-based pagination where full result sets are needed.
- [ ] **7. Run integration tests** — verify every endpoint works end-to-end against a v2 instance before cutting over production traffic.

---

## Upgrade

```bash
zrb upgrade --to v2
```