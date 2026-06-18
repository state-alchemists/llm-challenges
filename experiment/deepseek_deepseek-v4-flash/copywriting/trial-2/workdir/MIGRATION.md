# Migrating from Zrb CLI v1 to v2

Zrb CLI v2 introduces projects, paginated list responses, UUID-based task identifiers, and stricter authentication. This guide covers every breaking change and walks through the migration.

The v1 API will be deprecated 90 days after the v2 stable release. Plan your migration before then.

---

## Breaking Changes

### 1. All endpoints are prefixed with `/v2/`

Every endpoint path now starts with `/v2/`. Requests to v1 paths (`/tasks`) will receive HTTP 404.

**Before (v1):**

```http
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```http
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

### 2. Authentication header changed from `X-Auth-Token` to Bearer token

The request header for authentication has changed. The old `X-Auth-Token` header is no longer accepted; v2 requires a Bearer token in the standard `Authorization` header. Requests using the old header receive HTTP 401.

**Before (v1):**

```http
X-Auth-Token: <your_api_key>
```

**After (v2):**

```http
Authorization: Bearer <your_api_token>
```

Regenerate your API token from the dashboard — v2 tokens are separate from v1 keys.

### 3. Task ID changed from integer to UUID string

The `id` field is now a UUID string instead of an auto-incremented integer. All endpoints that accept an `id` parameter (GET, PUT, DELETE `/tasks/{id}`) now expect a UUID string. Stored integer IDs from v1 are not valid in v2.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

```http
GET /tasks/42
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

```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Field `done` renamed to `completed`

The boolean task status field has been renamed. Requests and responses now use `completed`.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

```http
PUT /tasks/42
Content-Type: application/json

{
  "done": true
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

```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Content-Type: application/json

{
  "completed": true
}
```

### 5. Task creation now requires `project_id`

Creating a task in v2 requires a `project_id` field in the request body. Omitting it returns HTTP 422. You must create a project first (or use an existing one) to obtain a `project_id`.

**Before (v1):**

```http
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2):**

```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List endpoints return a paginated envelope instead of a bare array

All list endpoints now return a paginated response envelope instead of a bare JSON array. The array lives in the `items` field, and pagination is cursor-based. v1's implicit offset-based pagination has been removed.

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
    {"id": "e5f67890-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Pass `?cursor=<next_cursor>` to fetch subsequent pages. Use `?limit=N` to control page size (default 20, max 100).

```http
GET /v2/tasks?cursor=cursor_xyz&limit=50
```

---

## Migration Checklist

Use this checklist to track your migration progress.

- [ ] **Regenerate API tokens.** Obtain v2 Bearer tokens from the dashboard. v1 `X-Auth-Token` values do not carry over.
- [ ] **Update all request headers.** Replace `X-Auth-Token: <key>` with `Authorization: Bearer <token>` in every client, script, and integration.
- [ ] **Prefix all endpoint paths with `/v2/`.** Batch-replace any hardcoded `https://api.zrb.dev/tasks` with `https://api.zrb.dev/v2/tasks`.
- [ ] **Migrate stored task IDs.** If your application stores task IDs (in a database, cache, or local state), plan a data migration from integer to UUID. v2 will assign new UUIDs — there is no 1:1 mapping from v1 integers.
- [ ] **Rename `done` to `completed` in all payloads.** Update both outgoing request bodies (POST/PUT) and response parsing logic. Search your codebase for `"done"` and `.done` references in task objects.
- [ ] **Add `project_id` to task creation.** Determine how to select or create a project on behalf of the user. Add `project_id` to every `POST /v2/tasks` request.
- [ ] **Rewrite list-response parsers.** Replace bare-array destructuring with access to `response.items`, and add pagination logic using `response.next_cursor`.
- [ ] **Update API client or SDK.** If you use a wrapper library, bump it to the v2-compatible version or upgrade inline calls.
- [ ] **Run integration tests.** Run your full test suite against a v2 staging environment. Verify authentication, CRUD, pagination, and error handling (HTTP 401, 404, 422).

## Upgrade

```bash
# Install or upgrade to Zrb CLI v2
pip install --upgrade zrb-cli
```

After upgrading, verify the version:

```bash
zrb --version
# Expected: 2.x.x
```

Then run your migration checklist and point clients at the `/v2/` base URL.
