# Migrating from Zrb CLI v1 to v2

This guide covers every breaking change in Zrb CLI v2 and how to update your integration code.

## Table of Contents

1. [Base URL Prefix](#base-url-prefix)
2. [Authentication Header](#authentication-header)
3. [Task ID Type](#task-id-type)
4. [Task Field Rename: `done` to `completed`](#task-field-rename-done-to-completed)
5. [Task Creation Requires `project_id`](#task-creation-requires-project_id)
6. [Paginated List Responses](#paginated-list-responses)
7. [Migration Checklist](#migration-checklist)

---

## Base URL Prefix

All endpoints are now prefixed with `/v2/`.

**Breaking change:** Requests to unversioned paths (e.g. `/tasks`) will 404.

### Before (v1)

```bash
curl -H "X-Auth-Token: <token>" \
  https://api.zrb.io/tasks
```

### After (v2)

```bash
curl -H "Authorization: Bearer <token>" \
  https://api.zrb.io/v2/tasks
```

---

## Authentication Header

The header name and format have changed.

**Breaking change:** `X-Auth-Token` is no longer accepted. Requests using it will receive HTTP 401.

### Before (v1)

```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.io/tasks
```

### After (v2)

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.io/v2/tasks
```

---

## Task ID Type

Task identifiers have changed from auto-incrementing integers to UUID strings.

**Breaking change:** If your code assumes `id` is an integer or uses numeric comparison, it will fail.

### Before (v1)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

```python
# v1 client code
task_id = 42
assert isinstance(task_id, int)
```

### After (v2)

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
# v2 client code
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
assert isinstance(task_id, str)
```

---

## Task Field Rename: `done` to `completed`

The boolean field indicating task completion has been renamed.

**Breaking change:** `done` is no longer a valid field in requests or responses. Using it in a request body will silently ignore the field or cause unexpected behavior.

### Before (v1)

```json
{
  "id": 1,
  "title": "Ship v1",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

```bash
# Update a task (v1)
curl -X PUT https://api.zrb.io/tasks/1 \
  -H "X-Auth-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

### After (v2)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Ship v2",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

```bash
# Update a task (v2)
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

---

## Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it will return HTTP 422.

**Breaking change:** v1 allowed creating tasks with only a `title`. v2 rejects requests without `project_id`.

### Before (v1)

```bash
curl -X POST https://api.zrb.io/tasks \
  -H "X-Auth-Token: <token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

### After (v2)

```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

## Paginated List Responses

List endpoints no longer return a bare array. They return a paginated envelope containing `items`, `total`, and `next_cursor`.

**Breaking change:** If your code assumes `GET /tasks` returns an array, it will break when accessing properties like `.length` or `[0]`.

### Before (v1)

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

```python
# v1 client code
response = requests.get("https://api.zrb.io/tasks", headers=auth)
tasks = response.json()
for task in tasks:
    print(task["title"])
```

### After (v2)

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

```python
# v2 client code
response = requests.get("https://api.zrb.io/v2/tasks", headers=auth)
page = response.json()
for task in page["items"]:
    print(task["title"])

# Fetch next page if present
if page.get("next_cursor"):
    next_response = requests.get(
        "https://api.zrb.io/v2/tasks",
        headers=auth,
        params={"cursor": page["next_cursor"]}
    )
```

---

## Migration Checklist

Use this checklist to ensure your code is fully migrated:

- [ ] **Update base URL:** Prefix all endpoint paths with `/v2/`.
- [ ] **Update auth header:** Replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Update Task ID handling:** Treat `id` as a UUID string, not an integer.
- [ ] **Rename `done` to `completed`:** Update request bodies and response parsing.
- [ ] **Add `project_id` to task creation:** Ensure every `POST /v2/tasks` request includes a `project_id`.
- [ ] **Update list response parsing:** Expect a paginated envelope (`{items, total, next_cursor}`) instead of a bare array.
- [ ] **Add pagination support:** Handle `next_cursor` and pass it as the `cursor` query parameter.
- [ ] **Run integration tests:** Verify your client works end-to-end against the v2 API.

---

## Upgrade Command

Install the latest CLI version to switch to v2:

```bash
pip install --upgrade zrb
```
