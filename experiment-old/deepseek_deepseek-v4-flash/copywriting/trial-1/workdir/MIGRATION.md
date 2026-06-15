# Zrb CLI v2 Migration Guide

This guide walks through every breaking change between Zrb CLI v1 and v2. It is written for developers maintaining existing v1 integrations — you know the current API and need exact before/after mappings to upgrade with confidence.

---

## Breaking Changes at a Glance

| # | Area | v1 | v2 | Impact |
|---|------|----|----|--------|
| 1 | Authentication | `X-Auth-Token` header | `Authorization: Bearer` header | All requests auth-fail until updated |
| 2 | URL prefix | `/tasks` | `/v2/tasks` | All endpoint URLs must be repointed |
| 3 | Task `id` type | Integer (e.g. `42`) | UUID string (e.g. `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`) | Storage, comparison, and URL construction break |
| 4 | Status field | `done` | `completed` | Reads and writes of task status silently misbehave |
| 5 | Task creation | `title` only | `title` + required `project_id` | POST without `project_id` returns HTTP 422 |
| 6 | List response | Bare array `[{...}, ...]` | Paginated envelope `{items, total, next_cursor}` | Any code assuming `response[0]` is a task breaks |

---

## 1. Authentication Header

**Change:** v1 uses a custom `X-Auth-Token` header. v2 uses the standard `Authorization: Bearer` header.

Sending an `X-Auth-Token` header to the v2 API returns **HTTP 401**.

**Before (v1):**

```http
X-Auth-Token: sk_live_abc123
GET /tasks
```

```python
# Python client (v1)
requests.get(
    "https://api.zrb.dev/tasks",
    headers={"X-Auth-Token": api_key}
)
```

```javascript
// JavaScript client (v1)
fetch("https://api.zrb.dev/tasks", {
    headers: { "X-Auth-Token": apiKey }
})
```

**After (v2):**

```http
Authorization: Bearer zrb_live_abc123
GET /v2/tasks
```

```python
# Python client (v2)
requests.get(
    "https://api.zrb.dev/v2/tasks",
    headers={"Authorization": f"Bearer {api_token}"}
)
```

```javascript
// JavaScript client (v2)
fetch("https://api.zrb.dev/v2/tasks", {
    headers: { "Authorization": `Bearer ${apiToken}` }
})
```

> **Note:** v2 tokens use the `zrb_` prefix. Generate a new token via the dashboard — v1 `sk_` keys are not forward-compatible.

---

## 2. URL Prefix

**Change:** All endpoints have moved under `/v2/`.

| Endpoint | v1 URL | v2 URL |
|----------|--------|--------|
| List Tasks | `GET /tasks` | `GET /v2/tasks` |
| Get Task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create Task | `POST /tasks` | `POST /v2/tasks` |
| Update Task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete Task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**

```python
BASE_URL = "https://api.zrb.dev"
response = requests.get(f"{BASE_URL}/tasks")
```

**After (v2):**

```python
BASE_URL = "https://api.zrb.dev/v2"
response = requests.get(f"{BASE_URL}/tasks")
```

---

## 3. Task ID: Integer → UUID

**Change:** Task `id` is now a UUID string rather than an auto-incrementing integer.

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
# v1 — integer comparison and URL construction
task_id = task["id"]                   # 42
url = f"{BASE_URL}/tasks/{task_id}"    # /tasks/42
assert task_id > 0                     # integer checks
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
# v2 — UUID string comparison and URL construction
task_id = task["id"]                               # "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
url = f"{BASE_URL}/tasks/{task_id}"                # /v2/tasks/a1b2c3d4-...
assert isinstance(task_id, str) and len(task_id) == 36
```

**Migration impact:**

- **Storage:** Columns typed as `INTEGER` must change to `UUID` or `VARCHAR(36)`.
- **Comparisons:** `task["id"] > 100` no longer applies; use string equality.
- **URLs:** Hard-coded / numeric task ID references break.

---

## 4. Field Renamed: `done` → `completed`

**Change:** The boolean status field is now `completed`. The old `done` field is absent in v2 responses.

**Before (v1):**

```python
# Reading status
task = response.json()
is_done = task["done"]

# Writing status
requests.put(f"{BASE_URL}/tasks/{task_id}", json={
    "done": True
})
```

**After (v2):**

```python
# Reading status
task = response.json()
is_done = task["completed"]

# Writing status
requests.put(f"{BASE_URL}/tasks/{task_id}", json={
    "completed": True
})
```

> **Warning:** The v2 API silently ignores unknown fields. Using `done` in a v2 request will not raise an error — the status simply won't update. Always verify by reading the task back.

---

## 5. Required `project_id` on Task Creation

**Change:** Creating a task now requires a `project_id` field. Omitting it returns **HTTP 422 Unprocessable Entity**.

**Before (v1):**

```python
# v1 — title only
response = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Write tests"
})
```

**After (v2):**

```python
# v2 — project_id required
response = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Write tests",
    "project_id": "proj_abc123"
})
```

Obtain `project_id` values from the new `GET /v2/projects` endpoint or the dashboard.

---

## 6. Paginated List Envelope

**Change:** List endpoints no longer return a bare array. They return a paginated envelope object with `items`, `total`, and `next_cursor`.

**Before (v1):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```python
# v1 — bare array, iterate directly
tasks = response.json()
for task in tasks:
    print(task["title"])
```

**After (v2):**

```json
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_...", "created_at": "..."},
    {"id": "c3d4...", "title": "Ship v2", "completed": true, "project_id": "proj_...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

```python
# v2 — navigate the envelope
data = response.json()
tasks = data["items"]
total = data["total"]

# Paginate if there are more results
cursor = data.get("next_cursor")
while cursor:
    response = requests.get(f"{BASE_URL}/tasks?cursor={cursor}")
    data = response.json()
    tasks.extend(data["items"])
    cursor = data.get("next_cursor")
```

**Query parameters for pagination:**
- `cursor` — opaque pagination token from `next_cursor` (optional)
- `limit` — page size, defaults to 20 (optional)

---

## Migration Checklist

Use this checklist to track your migration progress.

- [ ] **Generate a v2 API token.** Replace `X-Auth-Token` with `Authorization: Bearer <zrb_...>` in all requests.
- [ ] **Update all base URLs.** Change `https://api.zrb.dev/tasks` to `https://api.zrb.dev/v2/tasks` (and every other endpoint).
- [ ] **Migrate stored task IDs.** Convert any stored task IDs from integer to UUID. Update column types, in-memory structures, and any code that relies on numeric ordering or comparison.
- [ ] **Replace `done` with `completed`.** Update all reads (response parsing) and writes (request bodies) that refer to the status field.
- [ ] **Add `project_id` to task creation.** Determine the method for obtaining `project_id` (env var, config, user input) and add it to every `POST /v2/tasks` call.
- [ ] **Rewrite list-response handling.** Adjust code that assumes `response.json()` is a bare array to read `response.json()["items"]` instead. Add pagination iteration if you need all results.
- [ ] **Run integration tests.** Verify each endpoint in your staging environment before deploying to production.

---

## Upgrade Command

```bash
pip install --upgrade zrb==2.0.0
```

After upgrading, verify the installation:

```bash
zrb --version
# Expected: zrb 2.0.0
```
