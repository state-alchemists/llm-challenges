# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change from v1 to v2 and how to update your integration.

## Breaking Changes

### 1. Endpoint Prefix Changed

All endpoints now live under `/v2/`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before:**
```http
GET /tasks
```

**After:**
```http
GET /v2/tasks
```

---

### 2. Authentication Header Changed

The custom `X-Auth-Token` header is replaced with a standard Bearer token.

| v1 | v2 |
|---|---|
| `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` |

Requests using the old `X-Auth-Token` header will receive **HTTP 401**.

**Before:**
```http
X-Auth-Token: my_secret_key
```

**After:**
```http
Authorization: Bearer my_secret_token
```

---

### 3. Task `id` Is Now a UUID String

Task IDs changed from auto-incrementing integers to UUID strings.

**Before:**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

Update any code that stores, parses, or formats task IDs — integer math and string interpolation of numeric IDs will break.

---

### 4. Task Field `done` Renamed to `completed`

The boolean completion flag is renamed.

| v1 field | v2 field |
|---|---|
| `done` | `completed` |

**Before:**
```json
{ "id": 1, "title": "Ship v1", "done": true }
```

**After:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Ship v1", "completed": true }
```

Update all references to `task.done` → `task.completed`.

---

### 5. Task Creation Requires `project_id`

Creating a task now requires an associated project. Omitting `project_id` returns **HTTP 422**.

**Before:**
```json
POST /tasks
{ "title": "New task" }
```

**After:**
```json
POST /v2/tasks
{ "title": "New task", "project_id": "proj_abc123" }
```

If you do not already use projects, you will need to create one first:

```http
POST /v2/projects
{ "name": "My Project" }
```

---

### 6. List Response Is Now Paginated

List endpoints no longer return a bare array. They return an envelope with pagination metadata.

**Before:**
```json
GET /tasks
[
  { "id": 1, "title": "Buy milk", "done": false },
  { "id": 2, "title": "Ship v1", "done": true }
]
```

**After:**
```json
GET /v2/tasks
{
  "items": [
    { "id": "...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123" },
    { "id": "...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123" }
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

Update code that iterates over the list response directly — access `response.items` instead. To fetch subsequent pages, pass `?cursor=<next_cursor>` on the next request.

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Update task ID handling — change integer fields/variables to string (UUID)
- [ ] Rename all `done` field references to `completed` in task objects
- [ ] Ensure every task creation call includes `project_id`
- [ ] Update list response parsing — access `items` array from envelope
- [ ] Add pagination handling using `next_cursor` if you list all tasks
- [ ] Update any stored task ID references (database fields, cache keys, etc.)
- [ ] Run integration tests against the v2 endpoint to verify

---

## Upgrade Command

```bash
rbx-cli upgrade --version v2
```
