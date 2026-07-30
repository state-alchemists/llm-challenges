# Zrb CLI: v1 → v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter auth conventions. All v1 endpoints will continue to serve existing data for a transition window, but new development should target v2 immediately.

## Breaking Changes at a Glance

| Change | v1 | v2 |
|---|---|---|
| Endpoint prefix | `/tasks` | `/v2/tasks` |
| Auth header | `X-Auth-Token` | `Authorization: Bearer` |
| Task `id` type | integer | UUID string |
| Task completion field | `done` | `completed` |
| Task creation | title only | requires `project_id` |
| List response format | bare array | paginated envelope |

---

## 1. Endpoint Prefix

All endpoints are now prefixed with `/v2/`. Requests to the bare `/tasks` path will return 404.

**v1 (old):**

```bash
curl https://api.zrb.dev/tasks
curl https://api.zrb.dev/tasks/42
curl -X POST https://api.zrb.dev/tasks
```

**v2 (new):**

```bash
curl https://api.zrb.dev/v2/tasks
curl https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X POST https://api.zrb.dev/v2/tasks
```

---

## 2. Authentication Header

The API key header `X-Auth-Token` has been replaced by a standard Bearer token in the `Authorization` header. Requests with the old header receive HTTP 401.

**v1 (old):**

```http
X-Auth-Token: your_api_key
```

```bash
curl -H "X-Auth-Token: your_api_key" https://api.zrb.dev/tasks
```

**v2 (new):**

```http
Authorization: Bearer your_api_token
```

```bash
curl -H "Authorization: Bearer your_api_token" https://api.zrb.dev/v2/tasks
```

> **Action required:** Generate a new Bearer token through the Zrb dashboard. v1 API keys will not work with v2.

---

## 3. Task ID: Integer → UUID

Task `id` values are now UUID strings instead of auto-incrementing integers. This affects `GET`, `PUT`, and `DELETE` calls that reference a specific task, and any code that stores or compares task IDs.

**v1 (old):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

```javascript
// Storing or referencing IDs
const taskId = 42;
fetch(`https://api.zrb.dev/tasks/${taskId}`)
```

**v2 (new):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

```javascript
const taskId = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
fetch(`https://api.zrb.dev/v2/tasks/${taskId}`)
```

> **Impact:** Any database column, local cache, or URL template that assumed an integer `id` must be widened to accept a UUID string. Migrate existing references by querying the v1 endpoint alongside v2 during the transition period.

---

## 4. Field Rename: `done` → `completed`

The task completion field has been renamed from `done` to `completed` in both requests and responses.

**v1 (old):**

```json
// Response
{
  "id": 42,
  "title": "Write tests",
  "done": true
}

// Request body (PUT)
{ "done": true }
```

```javascript
// Client code
if (task.done) { /* ... */ }
```

**v2 (new):**

```json
// Response
{
  "id": "a1b2c3d4-...",
  "title": "Write tests",
  "completed": true,
  "project_id": "proj_abc123"
}

// Request body (PUT)
{ "completed": true }
```

```javascript
if (task.completed) { /* ... */ }
```

> **All callers must update:** the `done` field does not exist in v2 responses, and sending `done` in a v2 request body will be ignored.

---

## 5. New Required Field: `project_id`

Creating a task now requires `project_id`. Omitting it returns HTTP 422.

**v1 (old):**

```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task"}'
```

**v2 (new):**

```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer your_api_token" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

> **Action required:** Obtain a valid `project_id` from the Zrb dashboard or the `GET /v2/projects` endpoint. Decide how to assign tasks to projects — this may involve UI changes and a default-project strategy for existing workflows.

---

## 6. List Response Format: Bare Array → Paginated Envelope

List endpoints no longer return a bare JSON array. All v2 list responses use a paginated envelope with `items`, `total`, and `next_cursor`. Cursor-based pagination replaces offset/limit iteration.

**v1 (old) — GET /tasks:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```javascript
fetch("https://api.zrb.dev/tasks")
  .then(r => r.json())
  .then(tasks => tasks.forEach(t => render(t)));
```

**v2 (new) — GET /v2/tasks:**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6a7b8-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

```javascript
fetch("https://api.zrb.dev/v2/tasks")
  .then(r => r.json())
  .then(({ items, total, next_cursor }) => {
    items.forEach(t => render(t));
    if (next_cursor) {
      // Store cursor for "load more"
    }
  });
```

**Pagination pattern (v2):**

```bash
# First page (default limit: 20)
GET /v2/tasks

# Subsequent pages
GET /v2/tasks?cursor=cursor_xyz
GET /v2/tasks?cursor=next_cursor&limit=50
```

---

## Migration Checklist

- [ ] **Update endpoint URLs** — prepend `/v2/` to all API paths (`/tasks` → `/v2/tasks`).
- [ ] **Replace auth header** — swap `X-Auth-Token` for `Authorization: Bearer`. Generate a new Bearer token from the Zrb dashboard.
- [ ] **Handle UUID IDs** — widen any `id` storage, comparison, or serialization to accept UUID strings. Remove assumptions about integer auto-increment.
- [ ] **Rename `done` → `completed`** — update all request payloads (POST/PUT) and response parsing that reference the task completion field.
- [ ] **Add `project_id` to task creation** — obtain a project ID and include it in every `POST /v2/tasks` body. Handle HTTP 422 if omitted.
- [ ] **Update list response parsing** — unwrap the paginated envelope (`response.items` instead of `response` directly). Add cursor-based pagination logic where needed.
- [ ] **Test against v2** — run integration tests against the v2 endpoints. Verify 401 for old auth, 422 for missing `project_id`, and 404 for bare `/tasks`.

---

## Upgrade

```bash
npm install -g @zrb/cli@latest
# or, if using the Docker image:
docker pull zrb/cli:latest
```

After upgrading, regenerate your Bearer token and update your environment variables:

```bash
# Old (v1)
export ZRB_API_KEY=your_api_key

# New (v2)
export ZRB_API_TOKEN=your_bearer_token
export ZRB_API_BASE=https://api.zrb.dev/v2
```
