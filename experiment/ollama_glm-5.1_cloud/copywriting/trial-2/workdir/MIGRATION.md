# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. These changes require updates to your client code — this guide covers every breaking change with before/after examples and a step-by-step checklist.

---

## Breaking Changes

### 1. Endpoint prefix

All endpoints now live under `/v2/`. Requests to the old paths will receive `404`.

**Before (v1):**

```http
GET /tasks
POST /tasks
GET /tasks/42
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Action:** Update every request URL to include the `/v2` prefix.

---

### 2. Authentication header

The `X-Auth-Token` header is removed. Requests carrying it will receive `401 Unauthorized`.

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

**Action:** Replace all `X-Auth-Token` headers with `Authorization: Bearer <token>`.

---

### 3. Task `id` type changed from integer to UUID string

The `id` field is now a UUID string instead of an auto-assigned integer.

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

**Action:** Update any code that stores, compares, or serializes task IDs as integers. URL path parameters referencing a task ID must now accept UUID strings.

---

### 4. Field `done` renamed to `completed`

The boolean field `done` is now `completed`.

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

**Action:** Replace all reads and writes of the `done` field with `completed`. This affects both response parsing and update request bodies.

---

### 5. `project_id` is now required on task creation

`POST /v2/tasks` requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before (v1):**

```json
{
  "title": "New task title"
}
```

**After (v2):**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Action:** Add `project_id` to every task creation request. Determine the correct project ID for each task before migrating.

---

### 6. List responses use a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`. Subsequent pages are fetched by passing `?cursor=<next_cursor>`.

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
    {"id": "a1b2c3...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Fetching the next page:

```http
GET /v2/tasks?cursor=cursor_xyz
```

**Action:** Update all list-response parsing to read from the `items` array inside the envelope. Implement cursor-based pagination if you need to retrieve more than the default 20 results per page.

---

## Migration Checklist

Follow these steps in order. Verify each step before moving on.

1. **Update authentication** — Replace `X-Auth-Token` with `Authorization: Bearer <token>` in all requests.
2. **Update endpoint URLs** — Add the `/v2` prefix to every endpoint path.
3. **Update task ID handling** — Change all ID storage, comparison, and serialization from integer to UUID string.
4. **Rename `done` → `completed`** — Update field access in both read (response parsing) and write (update request bodies).
5. **Add `project_id` to task creation** — Supply a valid `project_id` in every `POST /v2/tasks` request body.
6. **Adapt list response parsing** — Read task arrays from the `items` field of the paginated envelope instead of treating the response body as a bare array.
7. **Implement cursor pagination** — If you fetch more than 20 tasks, loop through pages using the `next_cursor` value. Stop when `next_cursor` is absent or `null`.
8. **Test end-to-end** — Run your integration tests against the v2 API. Verify create, read, update, delete, and list flows.

---

## Upgrade

```bash
npm install zrb@2
```