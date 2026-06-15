# Zrb CLI v1 to v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and the exact code changes required to migrate.

---

## Breaking Changes

### 1. Endpoint URLs now require `/v2/` prefix

All API paths must be prefixed with `/v2/`. Requests to the legacy root paths will be rejected.

**Before (v1):**
```bash
curl https://api.zrb.example/tasks
curl https://api.zrb.example/tasks/42
```

**After (v2):**
```bash
curl https://api.zrb.example/v2/tasks
curl https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication header changed to Bearer token

`X-Auth-Token` is no longer accepted. v2 requires an `Authorization` header with a Bearer token.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.example/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.example/v2/tasks
```

> **Impact:** Requests sent with the old `X-Auth-Token` header will receive **HTTP 401 Unauthorized**.

---

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of auto-incrementing integers. Update any client-side logic that assumes integer IDs.

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

> **Impact:** Change ID storage from `number` to `string`, and update any URL construction that relied on numeric IDs.

---

### 4. Task field `done` renamed to `completed`

The boolean flag indicating task completion has been renamed.

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

> **Impact:** Update request payloads, deserialization logic, and any conditional checks in your codebase that reference the `done` field.

---

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` will return **HTTP 422 Unprocessable Entity**.

**Before (v1):**
```bash
curl -X POST https://api.zrb.example/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.example/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

> **Impact:** Ensure you have a valid `project_id` before calling `POST /v2/tasks`.

---

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope with `items`, `total`, and `next_cursor`.

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
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

> **Impact:** Update deserialization to read from `.items` instead of the root array. Pass `?cursor=<next_cursor>` to paginate through large result sets.

---

## Step-by-Step Migration Checklist

- [ ] Update all API request URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] Migrate `id` fields from `number` to `string` (UUID) throughout your data models and URLs.
- [ ] Rename all references from `done` to `completed` in payloads, models, and UI logic.
- [ ] Obtain valid `project_id` values and add `project_id` to every task creation request.
- [ ] Rewrite list-task deserialization to unwrap the `items` array from the paginated envelope.
- [ ] Add cursor-based pagination handling if you iterate over large task lists.
- [ ] Run your integration test suite against the v2 endpoints to verify the migration.

---

## Upgrade Command

Install the latest v2 CLI globally:

```bash
npm install -g @zrb/cli@latest
```

or via your preferred package manager:

```bash
yarn global add @zrb/cli@latest
# or
pnpm add -g @zrb/cli@latest
```
