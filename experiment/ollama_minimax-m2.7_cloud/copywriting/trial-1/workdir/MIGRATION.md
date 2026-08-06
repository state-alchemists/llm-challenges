# Zrb CLI Migration Guide: v1 → v2

v2 introduces projects, cursor-based pagination, and stricter authentication. Several v1 conventions have changed in breaking ways.

**If you are on v1, read every section below before upgrading.** A step-by-step checklist is at the end.

---

## 1. URL Prefix

All endpoints now carry a `/v2/` prefix. Calling the old paths without the prefix returns `404`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

---

## 2. Authentication Header

The auth header has changed. `X-Auth-Token` is no longer accepted; requests using it will receive `401 Unauthorized`.

**v1 — no longer works:**
```http
X-Auth-Token: your_api_key_here
```

**v2 — correct:**
```http
Authorization: Bearer your_api_token_here
```

Update any hardcoded header values or environment variable names referencing `X-Auth-Token`.

---

## 3. Task `id` Type: Integer → UUID

The `id` field is now a UUID string instead of an integer. This affects how you parse responses and how you construct URLs.

**v1 response:**
```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "..." }
```

**v2 response:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "..." }
```

In v1 you might have written:
```python
task_id = data["id"]       # int
url = f"/tasks/{task_id}"  # "/tasks/42"
```

In v2, `task_id` is a string:
```python
task_id = data["id"]       # "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
url = f"/v2/tasks/{task_id}"
```

Update any code that expects `id` to be an integer (type assertions, database columns, URL construction, cache keys).

---

## 4. Field Renamed: `done` → `completed`

The task completion flag has been renamed.

**v1:**
```json
{ "id": 1, "title": "Ship v1", "done": true, "created_at": "..." }
```

**v2:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
```

Any code referencing `task["done"]` must change to `task["completed"]`.

---

## 5. `project_id` Required on Task Creation

Creating a task now requires a `project_id`. Omitting it returns `422 Unprocessable Entity`.

**v1 request — no longer valid:**
```json
POST /tasks
{ "title": "New task title" }
```

**v2 request:**
```json
POST /v2/tasks
{ "title": "New task title", "project_id": "proj_abc123" }
```

Retrieve your `project_id` values from `GET /v2/projects` (or via the dashboard) before deploying v2. If you rely on a default project, query it explicitly rather than relying on an implicit default.

---

## 6. List Response: Paginated Envelope

List endpoints no longer return a bare array. They return a wrapping envelope with `items`, `total`, and `next_cursor`.

**v1 response:**
```json
GET /tasks
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**v2 response:**
```json
GET /v2/tasks
{
  "items": [
    { "id": "...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Iterating pages:**
```python
# v1: iterate the list directly
tasks = response.json()

# v2: unwrap the envelope
data = response.json()
tasks = data["items"]
cursor = data["next_cursor"]
```

Pass `?cursor=cursor_xyz` on the next request to fetch the following page. The `limit` query param controls page size (default 20).

---

## Migration Checklist

Run through these in order before deploying against a v2 endpoint.

- [ ] Replace all endpoint URLs: prepend `/v2` to every path
- [ ] Replace the auth header: `X-Auth-Token` → `Authorization: Bearer <token>`
- [ ] Update `id` handling: change integer assumptions to string/UUID
- [ ] Rename `done` to `completed` in every task read/write
- [ ] Add `project_id` to every task creation request
- [ ] Update list iteration: unwrap `items` from `{ items, total, next_cursor }`
- [ ] Add cursor-based pagination to any code that pages through list results
- [ ] Retrieve `project_id` values for all projects you use (via `GET /v2/projects`)
- [ ] Update any environment variables or secrets storing `X-Auth-Token`
- [ ] Run integration tests against a v2 staging environment before production rollout

---

## Upgrade Command

```bash
npm install -g @zrb/cli@latest
```

Or, if you use the alternative installer:

```bash
brew upgrade zrb
```
