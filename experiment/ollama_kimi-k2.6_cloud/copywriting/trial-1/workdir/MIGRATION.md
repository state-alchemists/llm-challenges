# Zrb CLI v1 → v2 Migration Guide

This guide walks you through every breaking change in Zrb CLI v2 and shows exactly what to change in your code.

---

## Table of Contents

1. [Breaking Changes](#breaking-changes)
   - [1. API Version Prefix](#1-api-version-prefix)
   - [2. Authentication Header](#2-authentication-header)
   - [3. Task IDs Are Now UUIDs](#3-task-ids-are-now-uuids)
   - [4. `done` Renamed to `completed`](#4-done-renamed-to-completed)
   - [5. Task Creation Requires `project_id`](#5-task-creation-requires-project_id)
   - [6. List Endpoints Return Paginated Envelope](#6-list-endpoints-return-paginated-envelope)
2. [Migration Checklist](#migration-checklist)
3. [Upgrade Command](#upgrade-command)

---

## Breaking Changes

### 1. API Version Prefix

All endpoints are now prefixed with `/v2/`. Requests to the old unprefixed paths will not reach the v2 API.

**Before (v1):**
```bash
curl https://api.zrb.io/tasks
curl https://api.zrb.io/tasks/42
```

**After (v2):**
```bash
curl https://api.zrb.io/v2/tasks
curl https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header

The `X-Auth-Token` header is removed. v2 uses a standard Bearer token in the `Authorization` header. Requests with `X-Auth-Token` will receive HTTP 401.

**Before (v1):**
```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.io/tasks
```

```python
headers = {"X-Auth-Token": api_key}
```

**After (v2):**
```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.io/v2/tasks
```

```python
headers = {"Authorization": f"Bearer {api_token}"}
```

---

### 3. Task IDs Are Now UUIDs

The `id` field changed from an auto-assigned integer to a UUID string. This affects every endpoint that references a task by ID, as well as how you store and compare IDs in your application.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

```python
# Storing and comparing integer IDs
task_id = 42
if task_id > 0:
    print("Valid task")
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

```python
import uuid

# Storing and comparing UUID strings
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
if uuid.UUID(task_id):
    print("Valid task")
```

---

### 4. `done` Renamed to `completed`

The boolean field on the Task object is renamed from `done` to `completed`. This affects both the response payload and the update request body.

**Before (v1):**
```json
// Response
{
  "id": 1,
  "title": "Ship v1",
  "done": true,
  "created_at": "..."
}
```

```bash
# Update task
curl -X PUT https://api.zrb.io/tasks/1 \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "Updated title", "done": true}'
```

```python
if task["done"]:
    print("Task finished")
```

**After (v2):**
```json
// Response
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Ship v1",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "..."
}
```

```bash
# Update task
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "Updated title", "completed": true}'
```

```python
if task["completed"]:
    print("Task finished")
```

---

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` field. Omitting it returns HTTP 422.

**Before (v1):**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

```python
payload = {"title": "New task title"}
```

**After (v2):**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

```python
payload = {
    "title": "New task title",
    "project_id": "proj_abc123"
}
```

---

### 6. List Endpoints Return Paginated Envelope

`GET /tasks` used to return a bare array. It now returns a paginated envelope with `items`, `total`, and `next_cursor`. You must update any code that iterates the response directly.

**Before (v1):**
```bash
curl https://api.zrb.io/tasks \
  -H "X-Auth-Token: <your_api_key>"
```

```json
// Response
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```python
import requests

resp = requests.get("https://api.zrb.io/tasks", headers={"X-Auth-Token": api_key})
tasks = resp.json()
for task in tasks:
    print(task["title"])
```

**After (v2):**
```bash
curl "https://api.zrb.io/v2/tasks?limit=20" \
  -H "Authorization: Bearer <your_api_token>"
```

```json
// Response
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-f6a7-8901-bcde-f12345678901", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

```python
import requests

resp = requests.get(
    "https://api.zrb.io/v2/tasks",
    headers={"Authorization": f"Bearer {api_token}"},
    params={"limit": 20}
)
data = resp.json()
tasks = data["items"]
for task in tasks:
    print(task["title"])

# Paginate if needed
next_cursor = data.get("next_cursor")
while next_cursor:
    resp = requests.get(
        "https://api.zrb.io/v2/tasks",
        headers={"Authorization": f"Bearer {api_token}"},
        params={"limit": 20, "cursor": next_cursor}
    )
    data = resp.json()
    for task in data["items"]:
        print(task["title"])
    next_cursor = data.get("next_cursor")
```

---

## Migration Checklist

Use this checklist to ensure every breaking change is addressed in your codebase before upgrading to v2.

- [ ] **Update all API URLs** to include the `/v2/` prefix.
- [ ] **Replace authentication headers** — swap `X-Auth-Token` for `Authorization: Bearer <token>` everywhere.
- [ ] **Update ID handling** — change task ID variables from integers to UUID strings; update any validation or comparison logic.
- [ ] **Rename `done` to `completed`** in all JSON payloads, response parsing, and conditional logic.
- [ ] **Add `project_id` to task creation** — every `POST /v2/tasks` request must include a valid `project_id`.
- [ ] **Handle paginated list responses** — wrap direct array access with `.items` and implement cursor-based pagination if you rely on full data sets.
- [ ] **Update tests and mocks** to reflect the new response shapes and required fields.
- [ ] **Verify error handling** — expect HTTP 401 for old auth headers and HTTP 422 for missing `project_id`.

---

## Upgrade Command

Install or upgrade to the latest v2 CLI:

```bash
pip install --upgrade zrb-cli
```

After installation, verify the version:

```bash
zrb --version
```

---

*Need help? Open a discussion in the [Zrb CLI Community](https://github.com/zrb-io/zrb-cli/discussions).*
