# Migrating from Zrb API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change and walks through what you need to update in your client code.

## Breaking Changes at a Glance

| # | Area | v1 | v2 |
|---|------|----|----|
| 1 | Endpoint path | `/tasks` | `/v2/tasks` |
| 2 | Authentication | `X-Auth-Token` header | `Authorization: Bearer` header |
| 3 | Task ID type | integer | UUID string |
| 4 | Task field `done` | `done: bool` | `completed: bool` |
| 5 | Task creation | `project_id` optional | `project_id` required |
| 6 | List response | bare array | paginated envelope |

---

## 1. Endpoint Paths — All Routed Under `/v2/`

Every endpoint has moved from `/tasks` to `/v2/tasks`. Requests to the old paths will fail (the v1 endpoints are removed).

```diff
- POST /tasks
+ POST /v2/tasks
```

```diff
- GET /tasks/42
+ GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Action:** Update the base URL in your HTTP client configuration.

## 2. Authentication — From Custom Header to Bearer Token

The `X-Auth-Token` header is replaced by the standard `Authorization: Bearer` header. v2 rejects requests using the old header with HTTP 401.

**Before (v1):**

```
X-Auth-Token: sk-6a2f9b1c8e4d
```

**After (v2):**

```
Authorization: Bearer zp_6a2f9b1c8e4d
```

If you use an HTTP client (e.g., `curl`):

```bash
# v1
curl -H "X-Auth-Token: sk-..." https://api.zrb.dev/tasks

# v2
curl -H "Authorization: Bearer zp_..." https://api.zrb.dev/v2/tasks
```

**Action:** Replace the `X-Auth-Token` header with `Authorization: Bearer` and use your new v2 token. Generate a v2 token from the dashboard — v1 tokens are not accepted.

## 3. Task IDs — Integers Replaced by UUIDs

Task `id` is now a UUID string. All endpoints that reference a task by ID now expect a UUID, and all responses return a UUID.

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

If you store task IDs in a database, adjust the column type:

```sql
-- v1: INTEGER
-- v2: UUID / VARCHAR(36)
ALTER TABLE tasks ALTER COLUMN id TYPE UUID USING id::uuid;
```

If you reference hard-coded IDs in scripts, replace them:

```diff
- GET /tasks/42
+ GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Action:** Replace integer IDs with UUIDs. Update any schema, cache key, or URL that assumes an integer `id`.

## 4. `done` Renamed to `completed`

The `done` field on task objects is renamed to `completed`. The semantics are unchanged — it is still a boolean defaulting to `false`.

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

Update all references in your code:

```javascript
// v1
const isDone = task.done;

// v2
const isDone = task.completed;
```

When updating a task:

```diff
  PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
  {
    "title": "Updated title",
-   "done": true
+   "completed": true
  }
```

**Action:** Rename all reads and writes of `done` to `completed` in your code. The v2 API ignores the old `done` key — it does not fall back.

## 5. `project_id` Required on Task Creation

Creating a task in v2 requires a valid `project_id`. Omitting it returns HTTP 422.

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

If you do not already have a project, create one first via the dashboard or the new `POST /v2/projects` endpoint (not covered here), then use the returned `project_id`.

**Action:** Add `project_id` to every `POST /v2/tasks` request body. Validate the value before sending — a nonexistent project ID also returns HTTP 422.

## 6. List Responses — Bare Array Replaced by Paginated Envelope

List responses now return a paginated envelope instead of a raw array.

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
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Update your client:

```javascript
// v1 — response is the array
const tasks = response;

// v2 — response is the envelope
const tasks = response.items;
const total = response.total;
```

To paginate, pass `?cursor=<next_cursor>` and `?limit=<max>` (default 20):

```bash
curl -H "Authorization: Bearer zp_..." \
  "https://api.zrb.dev/v2/tasks?cursor=cursor_xyz&limit=50"
```

**Action:** Unwrap list responses through the envelope. Handle the `cursor` field for pagination instead of relying on page/offset parameters (v2 does not support page-based pagination).

---

## Migration Checklist

Use this checklist to track your migration progress:

- [ ] **Endpoint paths:** Update all request URLs from `/tasks` to `/v2/tasks`
- [ ] **Authentication:** Replace `X-Auth-Token` header with `Authorization: Bearer`; generate and deploy v2 tokens
- [ ] **Task ID type:** Update database schemas, cache keys, and hard-coded references from integer to UUID string
- [ ] **`done` → `completed`:** Rename the field everywhere it is read or written
- [ ] **`project_id`:** Add the required `project_id` to all task creation requests; create projects if needed
- [ ] **List pagination:** Unwrap responses via the envelope (`response.items`); implement cursor-based pagination
- [ ] **Stored IDs:** If you cache or persist task IDs, re-fetch or migrate them — v1 integer IDs do not carry over to v2

---

## Upgrade Command

```bash
npm install zrb@latest          # Node.js / JavaScript
pip install --upgrade zrb       # Python
```

Verify the installed version:

```bash
zrb --version
# 2.0.0
```
