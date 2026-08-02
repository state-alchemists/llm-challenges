# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change in Zrb v2 and the exact changes you need to make in your code.

---

## Breaking Changes

### 1. Base URL Path Prefix

All endpoints are now prefixed with `/v2/`.

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

`X-Auth-Token` is no longer accepted. You must use a Bearer token in the `Authorization` header.

**Before (v1):**
```bash
curl -H "X-Auth-Token: my-api-key" \
     https://api.zrb.io/tasks
```

```python
headers = {"X-Auth-Token": api_key}
requests.get("https://api.zrb.io/tasks", headers=headers)
```

**After (v2):**
```bash
curl -H "Authorization: Bearer my-api-key" \
     https://api.zrb.io/v2/tasks
```

```python
headers = {"Authorization": f"Bearer {api_key}"}
requests.get("https://api.zrb.io/v2/tasks", headers=headers)
```

> Requests with the old `X-Auth-Token` header will now receive **HTTP 401 Unauthorized**.

---

### 3. Task `id` Changed from Integer to UUID

Task identifiers are now UUID strings instead of auto-incrementing integers.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
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

Update any code that assumes `id` is an integer (e.g., numeric comparison, validation, type casting).

---

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion is now named `completed`.

**Before (v1):**
```json
{
  "title": "Updated title",
  "done": true
}
```

```python
if task["done"]:
    print("Finished")
```

**After (v2):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

```python
if task["completed"]:
    print("Finished")
```

---

### 5. Task Creation Now Requires `project_id`

Creating a task without a `project_id` now returns **HTTP 422 Unprocessable Entity**.

**Before (v1):**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer my-api-key" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

### 6. List Endpoints Return a Paginated Envelope

The list endpoint no longer returns a bare array. It returns an object with `items`, `total`, and `next_cursor`.

**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```python
tasks = response.json()  # list directly
for task in tasks:
    print(task["title"])
```

**After (v2):**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

```python
data = response.json()
tasks = data["items"]  # access the items key
for task in tasks:
    print(task["title"])

# Pagination
if data.get("next_cursor"):
    fetch_next_page(cursor=data["next_cursor"])
```

---

## Migration Checklist

Follow these steps in order to migrate your integration:

- [ ] Update all base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] Update any code that treats task `id` as an integer; validate or store IDs as UUID strings.
- [ ] Rename every occurrence of the `done` field to `completed` in request bodies and response parsing.
- [ ] Add `project_id` to all task creation payloads.
- [ ] Wrap list-response handling to read `response["items"]` instead of the raw list; implement cursor pagination if you paginate through results.
- [ ] Run integration tests to confirm all endpoints work as expected.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
npm install -g @zrb/cli@latest
```

Or update your package dependency:

```bash
npm install @zrb/cli@^2.0.0
```
