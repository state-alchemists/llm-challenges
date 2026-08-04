# Migrating from Zrb CLI v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change you need to handle, with before/after examples.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every API path now lives under `/v2/`. Requests to the old paths will return `404`.

**Before (v1)**

```bash
curl https://api.zrb.dev/tasks
curl https://api.zrb.dev/tasks/42
```

**After (v2)**

```bash
curl https://api.zrb.dev/v2/tasks
curl https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Migration tip:** If you set a base URL in a client or config, update it once:

```bash
# v1
BASE_URL=https://api.zrb.dev

# v2
BASE_URL=https://api.zrb.dev/v2
```

---

### 2. Authentication header changed from `X-Auth-Token` to `Authorization: Bearer`

The `X-Auth-Token` header is no longer accepted. Requests using it receive `HTTP 401`.

**Before (v1)**

```bash
curl -H "X-Auth-Token: my_api_key" https://api.zrb.dev/tasks
```

**After (v2)**

```bash
curl -H "Authorization: Bearer my_api_token" https://api.zrb.dev/v2/tasks
```

If you use an SDK or wrapper, look for where the auth header is constructed — the value itself (`my_api_key`) stays the same; only the header name and format change.

---

### 3. Task `id` type changed from integer to UUID string

Task IDs are no longer auto-incremented integers. They are now UUID strings. Any code that parses, stores, or compares task IDs as integers will break.

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

**What to check:**
- Database columns typed as `INTEGER` — migrate to `VARCHAR` or `UUID`.
- URL route patterns matching `\d+` — update to UUID patterns.
- Equality comparisons or hashmap keys assuming integer IDs.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now called `completed`. The old name is not accepted in requests and does not appear in responses.

**Before (v1)**

```json
// Create/update request
{ "title": "Ship v2", "done": true }

// Response
{ "id": 42, "title": "Ship v2", "done": true, "created_at": "..." }
```

**After (v2)**

```json
// Create/update request
{ "title": "Ship v2", "completed": true }

// Response
{ "id": "a1b2c3d4-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
```

**What to check:**
- Any deserialization code referencing `done` — rename to `completed`.
- Filtering or query logic like `?done=true` — not supported in v2; use `?completed=true` if query params are added later.

---

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns `HTTP 422`.

**Before (v1)**

```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: my_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2)**

```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer my_api_token" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

**What to check:**
- Every place you create tasks — add `project_id`.
- Seed scripts, fixtures, and test factories that construct task payloads.
- If you don't have a project yet, create one first via the projects API before creating tasks.

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It now returns an object with `items`, `total`, and `next_cursor` fields.

**Before (v1)**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2)**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6g7h8-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>`. Use `?limit=N` to control page size (default 20).

**What to check:**
- Any code that parses the response as a top-level array — change to parse `response.items`.
- Loops that assume all results arrive in one request — implement cursor-based pagination.
- Frontend components or serializers that iterate over the raw response — update to iterate over `.items`.

---

## Migration Checklist

- [ ] **Update base URL** — add `/v2/` prefix to all endpoint paths (or set `BASE_URL` once in your config).
- [ ] **Switch auth header** — replace `X-Auth-Token: <key>` with `Authorization: Bearer <key>`.
- [ ] **Update ID handling** — change task ID storage, comparison, and route matching from integer to UUID string.
- [ ] **Rename `done` to `completed`** — in serialization, deserialization, and any client-side logic.
- [ ] **Add `project_id` to task creation** — update every `POST /v2/tasks` payload; create projects first if needed.
- [ ] **Parse paginated envelope** — update all list-endpoint consumers to read `items` from the envelope and handle `next_cursor` pagination.
- [ ] **Run integration tests** — verify every endpoint with the v2 contract before cutting over.

---

## Upgrade

```bash
npm install -g zrb@2
```