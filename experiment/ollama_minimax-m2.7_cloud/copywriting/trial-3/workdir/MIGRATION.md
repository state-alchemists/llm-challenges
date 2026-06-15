# Zrb Task API v1 → v2 Migration Guide

v2 introduces projects, pagination, and stricter authentication. This guide walks through every breaking change with before/after examples.

**Audience:** developers already using v1. Assumes familiarity with REST APIs and JSON.

---

## Breaking Changes

### 1. URL Prefix Changed

All endpoints now live under `/v2/`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**
```bash
curl https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl https://api.zrb.io/v2/tasks
```

---

### 2. Authentication Header Changed

The `X-Auth-Token` header is no longer accepted. v2 uses Bearer token authentication.

| v1 | v2 |
|---|---|
| `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |

Requests with `X-Auth-Token` return **HTTP 401**.

**Before (v1):**
```bash
curl -H "X-Auth-Token: your_api_key" https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer your_api_token" https://api.zrb.io/v2/tasks
```

If you are setting the header in code:

**Before (v1):**
```python
headers = {"X-Auth-Token": api_key}
```

**After (v2):**
```python
headers = {"Authorization": f"Bearer {api_key}"}
```

---

### 3. Task `id` Is Now a UUID String

Task IDs changed from integers to UUID strings.

| v1 | v2 |
|---|---|
| `"id": 42` | `"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

This affects every endpoint that references a task ID — URL parameters, response bodies, and any code that parses or stores task IDs as integers.

**Before (v1):**
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "..."}
```

**After (v2):**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
```

If your code treats IDs as integers, update it to handle strings:

**Before (v1):**
```python
task_id = response["id"]
assert isinstance(task_id, int)
```

**After (v2):**
```python
task_id = response["id"]
assert isinstance(task_id, str)
```

---

### 4. Field `done` Renamed to `completed`

The boolean completion flag was renamed.

| v1 | v2 |
|---|---|
| `"done": true` | `"completed": true` |

Affected endpoints: GET task, PUT task, and any response or request body referencing task state.

**Before (v1):**
```json
{"id": 1, "title": "Ship v1", "done": true, "created_at": "..."}
```

**After (v2):**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
```

When updating a task:

**Before (v1):**
```json
PUT /tasks/42
{"done": true}
```

**After (v2):**
```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{"completed": true}
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires an associated project.

| v1 | v2 |
|---|---|
| `POST /tasks` with `{"title": "..."}` | `POST /v2/tasks` with `{"title": "...", "project_id": "..."}` |

Omitting `project_id` returns **HTTP 422**.

**Before (v1):**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "X-Auth-Token: key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

**Before (v1):**
```python
payload = {"title": "Write tests"}
```

**After (v2):**
```python
payload = {"title": "Write tests", "project_id": "proj_abc123"}
```

If you do not already use projects, create one first:

```bash
# Create a project (if Projects API is available)
curl -X POST https://api.zrb.io/v2/projects \
  -H "Authorization: Bearer key" \
  -d '{"name": "My Project"}'
```

---

### 6. List Endpoints Return a Paginated Envelope

List responses changed from a bare array to a wrapped envelope with pagination fields.

| v1 | v2 |
|---|---|
| `[{...}, {...}]` | `{"items": [...], "total": N, "next_cursor": "..."}` |

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
    {"id": "e5f6g7h8-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

Iterate with cursor-based pagination:

**Before (v1):**
```python
tasks = response.json()
for task in tasks:
    print(task["title"])
```

**After (v2):**
```python
envelope = response.json()
for task in envelope["items"]:
    print(task["title"])

# Follow next page
if envelope["next_cursor"]:
    next_resp = client.get("/v2/tasks", params={"cursor": envelope["next_cursor"]})
```

The `limit` query parameter controls page size (default 20):

```bash
curl "https://api.zrb.io/v2/tasks?limit=50"
```

---

## Migration Checklist

Run through these steps in order:

- [ ] **Update base URL** — add `/v2` prefix to every endpoint
- [ ] **Replace auth header** — `X-Auth-Token` → `Authorization: Bearer <token>`
- [ ] **Update ID handling** — change task ID type from `int` to `string` (UUID)
- [ ] **Rename `done` field** — replace `done` with `completed` in all request/response code
- [ ] **Add `project_id` to task creation** — fetch or create a project first if needed
- [ ] **Update list parsing** — unwrap `response["items"]` instead of using the array directly
- [ ] **Implement cursor pagination** — use `next_cursor` to fetch subsequent pages
- [ ] **Update integration tests** — point tests at v2 endpoints and update assertions
- [ ] **Update hardcoded URLs** — search for `/tasks` strings in your codebase
- [ ] **Check stored task IDs** — any persisted integer IDs are invalid in v2

---

## Upgrade Command

```bash
pip install --upgrade zrb
```
