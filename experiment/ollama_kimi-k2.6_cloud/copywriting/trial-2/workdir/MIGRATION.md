# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. All examples use `curl`; adapt them to your HTTP client or SDK accordingly.

---

## Breaking Changes

### 1. Endpoint prefix changed to `/v2/`

All task endpoints are now version-prefixed. Requests to the old unprefixed paths will 404.

**Before (v1):**
```bash
curl -X GET https://api.zrb.example/tasks
curl -X GET https://api.zrb.example/tasks/42
curl -X POST https://api.zrb.example/tasks
curl -X PUT https://api.zrb.example/tasks/42
curl -X DELETE https://api.zrb.example/tasks/42
```

**After (v2):**
```bash
curl -X GET https://api.zrb.example/v2/tasks
curl -X GET https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X POST https://api.zrb.example/v2/tasks
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication header changed

The custom `X-Auth-Token` header is removed. v2 requires a standard Bearer token in the `Authorization` header. Requests using `X-Auth-Token` will receive HTTP 401.

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

---

### 3. Task `id` changed from integer to UUID string

Task identifiers are no longer auto-incrementing integers. They are now UUID strings. Update any client-side storage, URL construction, or validation that expects an integer.

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

---

### 4. Task field `done` renamed to `completed`

The boolean status field is now called `completed`. Sending `done` in request bodies will be ignored or may cause validation errors.

**Before (v1) — reading a task:**
```json
{
  "id": 1,
  "title": "Ship v1",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — reading a task:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Ship v1",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Before (v1) — updating a task:**
```bash
curl -X PUT https://api.zrb.example/tasks/42 \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"done": true}'
```

**After (v2) — updating a task:**
```bash
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"completed": true}'
```

---

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` is no longer allowed and returns HTTP 422.

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
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

### 6. List endpoints return a paginated envelope

`GET /tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`. Pass `?cursor=<next_cursor>` to fetch subsequent pages.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.example/tasks
```

**Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.example/v2/tasks?limit=20"
```

**Response:**
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

Fetching the next page:
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.example/v2/tasks?limit=20&cursor=cursor_xyz"
```

---

## Step-by-Step Migration Checklist

Use this checklist to ensure a complete upgrade:

- [ ] **Update base URL paths** — prepend `/v2/` to all task endpoints.
- [ ] **Rotate authentication** — replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Migrate ID storage** — change any stored task IDs from integers to UUID strings; update URL builders and validations.
- [ ] **Rename `done` to `completed`** — update request bodies, response parsing, and any local model/struct definitions.
- [ ] **Add `project_id` to task creation** — identify or create the project to associate with new tasks; update all `POST /v2/tasks` calls.
- [ ] **Adopt paginated list parsing** — unwrap `items` from the list envelope; implement cursor-based pagination if you fetch more than one page.
- [ ] **Run integration tests** — verify each endpoint (`list`, `get`, `create`, `update`, `delete`) against the v2 API.
- [ ] **Update client libraries / SDKs** — if you maintain a wrapper, bump its major version and publish release notes.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g @zrb/cli@latest
# or
yarn global add @zrb/cli@latest
```

Verify the installation:

```bash
zrb --version
# Expected: 2.x.x
```
