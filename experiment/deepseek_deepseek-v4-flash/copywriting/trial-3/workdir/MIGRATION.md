# Zrb CLI v1 → v2 Migration Guide

## Overview

Zrb v2 introduces projects, cursor-based pagination, stricter authentication, and several field-level refinements. The v1 API will continue receiving security patches through **August 2026** and will be fully decommissioned on **December 31, 2026**.

This guide covers every breaking change and provides step-by-step instructions for upgrading.

---

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoints prefixed with `/v2/` | All URL paths must be updated |
| 2 | Auth header changed from `X-Auth-Token` to `Authorization: Bearer` | Every request header must change |
| 3 | Task `id` is now a UUID string (was integer) | ID lookups, caching, and stored references must be updated |
| 4 | Task field `done` renamed to `completed` | All read and write code referencing `done` must be changed |
| 5 | `project_id` is required on task creation | New task creation requires a project scope |
| 6 | List responses return a paginated envelope (was bare array) | All list-consumption code must unwrap the envelope and handle cursors |

---

## 1. Endpoint URL Prefix

All endpoints now live under `/v2/`. Requests to bare `/tasks` return a 404.

**Before (v1):**

```bash
curl -X GET "https://api.zrb.dev/tasks"
curl -X GET "https://api.zrb.dev/tasks/42"
curl -X POST "https://api.zrb.dev/tasks"
```

**After (v2):**

```bash
curl -X GET "https://api.zrb.dev/v2/tasks"
curl -X GET "https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
curl -X POST "https://api.zrb.dev/v2/tasks"
```

---

## 2. Authentication Header

The `X-Auth-Token` header has been replaced with the standard `Authorization: Bearer` scheme. Requests using the old header will receive an HTTP 401.

**Before (v1):**

```bash
curl -H "X-Auth-Token: <your_api_key>" "https://api.zrb.dev/tasks"
```

```python
# Python (requests)
headers = {"X-Auth-Token": "your_api_key"}
```

```javascript
// JavaScript (fetch)
const headers = { "X-Auth-Token": "your_api_key" };
```

**After (v2):**

```bash
curl -H "Authorization: Bearer <your_api_token>" "https://api.zrb.dev/v2/tasks"
```

```python
# Python (requests)
headers = {"Authorization": "Bearer your_api_token"}
```

```javascript
// JavaScript (fetch)
const headers = { "Authorization": "Bearer your_api_token" };
```

Tokens are issued per workspace and can be managed via the Zrb dashboard at `https://dashboard.zrb.dev/settings/tokens`.

---

## 3. Task ID: Integer → UUID String

Task identifiers are now UUID strings (v4). All `id` references — stored IDs, cache keys, URL construction, database foreign keys — must be changed from integer to string type.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

```python
task_id = 42
response = requests.get(f"https://api.zrb.dev/tasks/{task_id}")
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

```python
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
response = requests.get(f"https://api.zrb.dev/v2/tasks/{task_id}")
```

> **Migration note:** v2 does not provide an integer-to-UUID mapping endpoint. You will need to re-fetch your task list from v2 to build the new ID table, or reconcile via the `title` field during a zero-downtime migration window.

---

## 4. Field Rename: `done` → `completed`

The task field `done` has been renamed to `completed`. Both request bodies (`PUT`) and response parsing must use the new field name.

**Before (v1) — reading a task:**

```python
task = response.json()
if task["done"]:
    print("Task is complete")
```

**After (v2) — reading a task:**

```python
task = response.json()
if task["completed"]:
    print("Task is complete")
```

**Before (v1) — updating a task:**

```json
PUT /tasks/{id}
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) — updating a task:**

```json
PUT /v2/tasks/{id}
{
  "title": "Updated title",
  "completed": true
}
```

> **Note:** v2 returns a `422 Unprocessable Entity` if the request body includes `done` but omits `completed`.

---

## 5. New Required Field: `project_id`

Every task must now belong to a project. The `project_id` field is required on creation and mandatory in the request body.

**Before (v1):**

```bash
curl -X POST "https://api.zrb.dev/tasks" \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <key>" \
  -d '{"title": "New task"}'
```

**After (v2):**

```bash
curl -X POST "https://api.zrb.dev/v2/tasks" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

**Before (v1):**

```python
payload = {"title": "New task"}
response = requests.post("https://api.zrb.dev/tasks", json=payload)
```

**After (v2):**

```python
payload = {"title": "New task", "project_id": "proj_abc123"}
response = requests.post("https://api.zrb.dev/v2/tasks", json=payload)
```

Omitting `project_id` returns an HTTP 422 with a descriptive error body. You can list available projects via `GET /v2/projects`.

---

## 6. List Responses Return a Paginated Envelope

All list endpoints now return a paginated envelope instead of a bare array. You must unwrap the items and handle cursor-based pagination.

**Before (v1) — response:**

```json
GET /tasks
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**After (v2) — response:**

```json
GET /v2/tasks
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false},
    {"id": "c3d4...", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Before (v1) — client code:**

```python
tasks = response.json()       # bare list
for task in tasks:
    print(task["title"])
```

**After (v2) — client code:**

```python
data = response.json()
tasks = data["items"]         # wrapped in envelope
for task in tasks:
    print(task["title"])
```

**Pagination loop pattern (v2):**

```python
def fetch_all_tasks():
    tasks = []
    cursor = None
    while True:
        params = {"cursor": cursor, "limit": 100}
        data = requests.get("https://api.zrb.dev/v2/tasks", params=params).json()
        tasks.extend(data["items"])
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return tasks
```

The `limit` parameter controls page size (default 20, max 200). When `next_cursor` is `null`, there are no more pages.

---

## Migration Checklist

Use this checklist to track your migration progress. Tick off each item as you complete it.

- [ ] **Update all endpoint URLs** — replace `/tasks` with `/v2/tasks` everywhere (docs, SDKs, config files, curl scripts).
- [ ] **Switch authentication headers** — replace `X-Auth-Token` with `Authorization: Bearer <token>`. Generate new tokens from the dashboard.
- [ ] **Reconcile task IDs** — identify all code paths, caches, and databases that store task IDs as integers. Convert stored IDs to UUID strings, or plan a reconciliation window to rebuild the mapping.
- [ ] **Rename `done` → `completed`** — update all request bodies (`PUT`), response parsers, and client-side state references. Add a linter rule to catch stale `done` references.
- [ ] **Add `project_id` to task creation** — every `POST /v2/tasks` call must include `project_id`. Create a default project via the dashboard or the `POST /v2/projects` endpoint if your application does not use projects yet.
- [ ] **Unwrap list responses** — all code consuming `GET /v2/tasks` must read `data["items"]` instead of assuming a bare array.
- [ ] **Add pagination support** — implement cursor-handling for any code that needs the full task list. Update batch-processing scripts, exports, and UI pagination controls.
- [ ] **Update client-side type definitions** — if your project uses TypeScript types, JSON Schema, or Pydantic models, update the `id` type (`int` → `str`) and field name (`done` → `completed`), and add `project_id: str`.
- [ ] **Run integration tests** — execute your test suite against the v2 API in a staging environment before deploying to production.
- [ ] **Monitor error logs** — watch for HTTP 401 (`X-Auth-Token` still in use), 422 (`done` field or missing `project_id`), and 404 (bare `/tasks` URLs) during the rollout.

---

## Upgrade Command

Once you've completed the checklist, install the v2 CLI:

```bash
pip install --upgrade zrb
```

Verify the installation:

```bash
zrb --version
# Expected output: zrb 2.0.0 or later
```

For Docker users:

```bash
docker pull zrb/cli:2
```

For the API base URL, update your configuration:

```bash
zrb config set api_base_url https://api.zrb.dev/v2
```
