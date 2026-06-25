# Zrb CLI v1 to v2 Migration Guide

v2 introduces projects, improved pagination, and stricter authentication. This guide covers every breaking change and how to update your integration.

**Estimated migration time:** 15–30 minutes

---

## Breaking Changes

### 1. All Endpoints Moved to `/v2/` Prefix

Every endpoint now lives under `/v2/`. Requests to v1 paths return `404`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

### 2. Authentication Header Changed

The `X-Auth-Token` header is no longer accepted. v2 uses Bearer token authentication.

**v1:**
```http
X-Auth-Token: your_api_key_here
```

**v2:**
```http
Authorization: Bearer your_api_token_here
```

Requests with `X-Auth-Token` will receive `401 Unauthorized`.

### 3. Task `id` Is Now a UUID String

Task IDs changed from auto-incrementing integers to UUID strings.

**v1 response:**
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z"}
```

**v2 response:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
```

Update any code that parses or stores task IDs to handle UUID strings instead of integers.

### 4. Field `done` Renamed to `completed`

The task completion flag has a new name.

**v1:**
```json
{"done": true}
```

**v2:**
```json
{"completed": true}
```

Update field references in request bodies and response parsing.

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns `422 Unprocessable Entity`.

**v1:**
```http
POST /tasks
{"title": "New task"}
```

**v2:**
```http
POST /v2/tasks
{"title": "New task", "project_id": "proj_abc123"}
```

Before migrating, you need a `project_id` from an existing project or a newly created one. See the checklist below.

### 6. List Endpoints Return Paginated Envelope

List endpoints no longer return a bare array. They return a wrapper envelope with `items`, `total`, and `next_cursor`.

**v1:**
```json
[{"id": 1, "title": "Buy milk", "done": false, "created_at": "..."}]
```

**v2:**
```json
{
  "items": [{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}],
  "total": 1,
  "next_cursor": null
}
```

To fetch the next page, pass `?cursor=<next_cursor>` on the subsequent request. The `limit` query parameter controls page size (default 20).

Update your list-parsing logic to read `response.items` instead of the response root, and check `response.next_cursor` for pagination.

---

## Migration Checklist

1. **Update base URL** — prepend `/v2` to every endpoint path
2. **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer`
3. **Update ID handling** — change task ID variables from `int` to `str` (UUID)
4. **Update field names** — rename `done` → `completed` in all request/response code
5. **Create or identify a project** — obtain a `project_id` for use in task creation
6. **Update list parsing** — change array access to `response["items"]`; handle `response["next_cursor"]` for pagination
7. **Add `project_id` to task creation** — include `project_id` in `POST /v2/tasks` body
8. **Test all endpoints** — verify list, get, create, update, and delete work end-to-end

---

## Upgrade Command

```bash
pip install --upgrade zrb-cli
```
