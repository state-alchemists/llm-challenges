# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. All existing endpoints and data models have breaking changes — this guide covers every one.

---

## Breaking Changes Overview

| Change | Impact |
|---|---|
| Auth header format | Every request rejected with 401 if not updated |
| Endpoint path prefix `/v2/` | All URL strings must change |
| Task `id`: integer → UUID | Lookups, foreign keys, caches, and type checks break |
| `done` → `completed` | Reads and writes on `done` silently drop or error |
| `project_id` required on create | Existing creation code returns 422 |
| List responses: bare array → envelope | All response-parsing code must change |

---

## 1. Authentication Header

`X-Auth-Token` is removed. Use a Bearer token in the `Authorization` header.

**Before (v1)**

```
X-Auth-Token: sk-abc123
```

**After (v2)**

```
Authorization: Bearer zp_sk-abc123
```

Requests with the old header receive HTTP 401 with no body.

---

## 2. Endpoint Path Prefix

All endpoints are now prefixed with `/v2/`.

| Operation | v1 | v2 |
|---|---|---|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Example client update (curl)**

```bash
# v1
curl -H "X-Auth-Token: sk-abc123" https://api.zrb.dev/tasks

# v2
curl -H "Authorization: Bearer zp_sk-abc123" https://api.zrb.dev/v2/tasks
```

---

## 3. Task ID: Integer → UUID String

The `id` field is now a UUID string. Integer IDs are no longer accepted or returned.

**Before (v1)**

```json
{"id": 42, "title": "Write tests", "done": false}
```

**After (v2)**

```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123"}
```

**Key implications:**

- Cache keys, database references, and URL paths that embed integer IDs must be migrated to UUIDs.
- Type checks (`typeof id === "number"`, `isinstance(id, int)`) will fail — use string validation instead.
- Hard-coded task IDs in test fixtures or config files must be regenerated.

---

## 4. Field Rename: `done` → `completed`

The task completion field has been renamed.

**Before (v1)**

```json
{"done": true}
```

**After (v2)**

```json
{"completed": true}
```

**Reads:** Code that reads `task.done` will see `undefined`/`None` in v2 responses. Search your codebase and rename every reference.

**Writes:** Sending `"done": true` in a create or update request is silently ignored. The task will remain uncompleted.

**Example (JavaScript)**

```javascript
// v1
if (task.done) { /* … */ }

// v2
if (task.completed) { /* … */ }
```

**Example (Python)**

```python
# v1
response = requests.put(f"{base}/tasks/{tid}", json={"done": True})

# v2
response = requests.put(f"{base}/v2/tasks/{tid}", json={"completed": True})
```

---

## 5. Task Creation Requires `project_id`

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns HTTP 422 with `{"error": "project_id is required"}`.

You must either create a project first (see the Projects API) or obtain an existing project ID.

**Before (v1)**

```json
POST /tasks
{"title": "Buy milk"}
```

**After (v2)**

```json
POST /v2/tasks
{"title": "Buy milk", "project_id": "proj_abc123"}
```

**Migration strategy:** Retrieve the list of projects and pick one as your default, or create a dedicated project during setup, then pass `project_id` on every task create.

---

## 6. List Response Format: Paginated Envelope

All list endpoints now return a paginated envelope instead of a bare array.

**Before (v1)**

```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**After (v2)**

```json
{
  "items": [
    {"id": "a1b2…", "title": "Buy milk", "completed": false, "project_id": "proj_abc123"},
    {"id": "d4e5…", "title": "Ship v1", "completed": true, "project_id": "proj_abc123"}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Client changes:**

- Replace direct array iteration with `response.items` iteration.
- Implement cursor-based pagination: pass `?cursor=<next_cursor>` to fetch the next page. An absent or null `next_cursor` means the last page.
- The `total` field gives the count across all pages (use `limit` to control page size, default 20).

**Example (JavaScript)**

```javascript
// v1
const tasks = await fetch("/tasks").then(r => r.json());
tasks.forEach(t => console.log(t.title));

// v2
const { items, total, next_cursor } = await fetch("/v2/tasks?limit=50").then(r => r.json());
items.forEach(t => console.log(t.title));
if (next_cursor) {
  // fetch next page: /v2/tasks?cursor=<next_cursor>&limit=50
}
```

---

## Step-by-Step Migration Checklist

- [ ] **Regenerate API tokens.** Obtain v2 Bearer tokens through the account dashboard. The old `X-Auth-Token` values no longer work.
- [ ] **Update all auth headers.** Replace `X-Auth-Token` with `Authorization: Bearer` in every client, script, and configuration file.
- [ ] **Prefix all endpoint paths with `/v2/`.** Update every URL string (curl, HTTP client, SDK, CI scripts, integration configs).
- [ ] **Migrate task ID references.** Move integer IDs to UUIDs in caches, databases, foreign-key columns, test fixtures, and hard-coded configs. Regenerate any stored integer references via the v2 API.
- [ ] **Rename `done` → `completed`.** Audit every read (`task.done`, `task["done"]`) and every write (create/update payloads). Update serialization/deserialization code and UI components.
- [ ] **Add `project_id` to task creation.** Create or identify a project ID and include it in every `POST /v2/tasks` request. Add validation that `project_id` is present before sending.
- [ ] **Rewrite list-response parsing.** Switch from iterating the response directly to accessing `response.items`. Add pagination logic using `next_cursor` and `limit`.
- [ ] **Update type schemas.** Refresh any TypeScript types, Pydantic models, JSON schemas, or OpenAPI specs to match the v2 response shape.
- [ ] **Run integration tests.** Verify each endpoint against a v2 staging environment before cutting over production traffic.

---

## Upgrade

Run the following command to upgrade your CLI and associated tooling:

```bash
zrb upgrade --version 2.0.0
```

Once upgraded, verify the active version:

```bash
zrb --version
```

All existing scripts, env files, and SDKs referencing v1 must be updated per the checklist above before they will work against v2 servers.
