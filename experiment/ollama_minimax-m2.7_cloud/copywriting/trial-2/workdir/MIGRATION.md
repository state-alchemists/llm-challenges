# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Each section includes a before/after example and the minimum action required to migrate.

---

## Breaking Changes

### 1. Endpoint Path Prefix

All endpoints now live under `/v2/` instead of `/`.

**Before (v1)**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2)**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

**Action:** Prepend `/v2` to every endpoint path in your client code and any hardcoded URLs.

---

### 2. Authentication Header

The auth header has changed from a custom header to a standard Bearer token.

**Before (v1)**
```http
X-Auth-Token: <your_api_key>
```

**After (v2)**
```http
Authorization: Bearer <your_api_token>
```

**Action:** Update your HTTP client to send `Authorization: Bearer <token>` instead of `X-Auth-Token`. Requests with the old header will receive `401 Unauthorized`.

---

### 3. Task `id` is Now a UUID String

Task IDs are no longer integers — they are UUID strings.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "..." }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "..." }
```

**Action:** Update any code that parses or stores task IDs to expect a string in UUID format, not an integer. This affects GET, PUT, and DELETE calls where you construct the URL path.

---

### 4. Field Renamed: `done` → `completed`

The task completion flag has been renamed.

**Before (v1)**
```json
{ "title": "Ship v1", "done": true }
```

**After (v2)**
```json
{ "title": "Ship v2", "completed": true }
```

**Action:** Rename `done` to `completed` in all JSON request bodies and update any field references in your code.

---

### 5. Task Creation Requires `project_id`

Creating a task now requires associating it with a project. The `project_id` field is mandatory.

**Before (v1)**
```json
POST /tasks
{ "title": "New task" }
```

**After (v2)**
```json
POST /v2/tasks
{ "title": "New task", "project_id": "proj_abc123" }
```

**Action:** Every task create call must include a valid `project_id`. Omitting it returns `422 Unprocessable Entity`. You will need a project ID from your existing project setup or create one via the projects API (out of scope for this guide).

---

### 6. List Response is Paginated

List endpoints no longer return a bare array. They return a wrapper envelope with `items`, `total`, and `next_cursor`.

**Before (v1)**
```json
GET /tasks
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2)**
```json
GET /v2/tasks
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "e5f6g7h8-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>` as a query parameter.

**Action:** Update list-response parsing to read `response.items` instead of the root array. If you need all results, loop over pages using `next_cursor` until it is `null`.

---

## Migration Checklist

Run through these steps in order before deploying against a v2 API server:

- [ ] **Update endpoint paths** — add `/v2` prefix to every route (`/tasks` → `/v2/tasks`, etc.)
- [ ] **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update task ID handling** — change ID fields from `int` to `string` / UUID in all parse/serialize/URL-building code
- [ ] **Rename `done` to `completed`** — in all request/response JSON and code references
- [ ] **Add `project_id` to task creation** — every `POST /v2/tasks` body must include `"project_id": "<your_project_id>"`
- [ ] **Update list parsing** — read `response.items`, `response.total`, and `response.next_cursor` instead of a raw array; implement cursor-based pagination if you need all records
- [ ] **Update tests and fixtures** — replace integer IDs with UUID strings, update response shapes, add `project_id` where needed

---

## Upgrade Command

```bash
npm install zrb-cli@latest
# or
pip install zrb-cli --upgrade
```

Replace with whichever package manager your project uses.
