# Migrating from Zrb Task API v1 to v2

Zrb Task API v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change between v1 and v2, with before/after examples for each.

---

## Breaking Changes

### 1. All endpoints are prefixed with `/v2/`

Every endpoint path now starts with `/v2/`. Calls to the old paths (e.g. `GET /tasks`) will fail.

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

Update your base URL or path prefix in one place (e.g. an `API_BASE` constant) rather than per-call.

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it receive HTTP 401.

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

If you use an HTTP client with default headers, replace the `X-Auth-Token` default with an `Authorization: Bearer` default. If you construct headers per-request, update every call site.

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of auto-assigned integers. Any code that parses, stores, or validates task IDs as integers must be updated.

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

Check your data model, ORM column types, URL regexes, and any hardcoded test fixtures.

### 4. Field `done` renamed to `completed`

The boolean marking whether a task is finished is now called `completed` instead of `done`.

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

Search your codebase for the string `"done"` in serialisation/deserialisation logic, request builders, and conditional checks — rename each occurrence to `"completed"`.

### 5. Task creation requires `project_id`

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns HTTP 422.

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

Ensure your create-task forms and API wrappers always include `project_id`. If your integration auto-creates tasks, decide which project to assign them to before migrating.

### 6. List endpoints return a paginated envelope instead of a bare array

List responses are no longer plain arrays. They are wrapped in an envelope with `items`, `total`, and `next_cursor`. Pass `?cursor=<next_cursor>` to fetch the next page.

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
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Any code that iterates over the response directly (e.g. `for task in response`) must now iterate over `response["items"]`. To fetch all tasks, loop until `next_cursor` is `null`.

---

## Migration Checklist

- [ ] **Update base URL** — add the `/v2/` prefix to every endpoint path (or set it once in your client's base URL).
- [ ] **Switch auth header** — replace `X-Auth-Token: <key>` with `Authorization: Bearer <token>`. Remove any `X-Auth-Token` references.
- [ ] **Change task ID type** — update models, schemas, database columns, and URL patterns from integer to UUID string.
- [ ] **Rename `done` to `completed`** — update create/update request bodies, response parsers, and conditional logic.
- [ ] **Add `project_id` to task creation** — supply a `project_id` in every `POST /v2/tasks` request body.
- [ ] **Handle paginated list responses** — parse `items` from the envelope instead of treating the response as a bare array. Implement cursor-based pagination if you need more than the default 20 results per page.
- [ ] **Run your test suite** — verify all endpoint calls return expected status codes and shapes against the v2 API.
- [ ] **Remove v1 fallback paths** — once migration is complete, clean out any v1-compatible code, constants, or config.

---

## Upgrade

```bash
zrb upgrade --to v2
```