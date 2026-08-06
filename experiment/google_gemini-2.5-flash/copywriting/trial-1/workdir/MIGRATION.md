# Zrb CLI v1 to v2 Migration Guide

This guide outlines the breaking changes introduced in Zrb CLI v2 and provides step-by-step instructions and code examples to help you migrate your applications.

## Table of Contents

1.  [API Endpoint Prefix Change](#api-endpoint-prefix-change)
2.  [Authentication Header Update](#authentication-header-update)
3.  [Task ID Type Change](#task-id-type-change)
4.  [Task `done` Field Renamed to `completed`](#task-done-field-renamed-to-completed)
5.  [Task Creation Requires `project_id`](#task-creation-requires-project_id)
6.  [List Endpoints Return Paginated Data](#list-endpoints-return-paginated-data)
7.  [Migration Checklist](#migration-checklist)
8.  [Upgrade Command](#upgrade-command)

---

## 1. API Endpoint Prefix Change

All API endpoints in v2 are now prefixed with `/v2/`. This ensures versioning and allows for future API iterations.

### Before (v1)

```
GET /tasks
POST /tasks
GET /tasks/{id}
```

### After (v2)

```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
```

### Code Example

**Before (v1)**

```python
import requests

api_key = "your_v1_api_key"
base_url = "https://api.zrb.com"

# List tasks
response = requests.get(f"{base_url}/tasks", headers={"X-Auth-Token": api_key})
tasks = response.json()
print(tasks)

# Create a task
new_task = {"title": "Learn Zrb v2"}
response = requests.post(f"{base_url}/tasks", json=new_task, headers={"X-Auth-Token": api_key})
created_task = response.json()
print(created_task)
```

**After (v2)**

```python
import requests

api_token = "your_v2_api_token" # Note: API key format changed
base_url = "https://api.zrb.com"

# List tasks
response = requests.get(f"{base_url}/v2/tasks", headers={"Authorization": f"Bearer {api_token}"})
# Note: Response structure changed to paginated envelope
tasks_data = response.json()
print(tasks_data)

# Create a task
new_task = {"title": "Learn Zrb v2", "project_id": "proj_abc123"} # Note: project_id required
response = requests.post(f"{base_url}/v2/tasks", json=new_task, headers={"Authorization": f"Bearer {api_token}"})
created_task = response.json()
print(created_task)
```

---

## 2. Authentication Header Update

The authentication mechanism has been updated in v2. The `X-Auth-Token` header is no longer supported. All requests must now use a Bearer token in the `Authorization` header. Requests using the old header will receive an HTTP 401 Unauthorized response.

### Before (v1)

```
X-Auth-Token: <your_api_key>
```

### After (v2)

```
Authorization: Bearer <your_api_token>
```

### Code Example

**Before (v1)**

```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
```

**After (v2)**

```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
```

---

## 3. Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string. This change affects any operations that reference tasks by their ID, such as `GET /tasks/{id}`, `PUT /tasks/{id}`, and `DELETE /tasks/{id}`.

### Before (v1)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
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

### Code Example

**Before (v1)**

```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
task_id = 42 # Integer ID
response = requests.get(f"https://api.zrb.com/tasks/{task_id}", headers=headers)
task = response.json()
print(task)
```

**After (v2)**

```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890" # UUID string ID
response = requests.get(f"https://api.zrb.com/v2/tasks/{task_id}", headers=headers)
task = response.json()
print(task)
```

---

## 4. Task `done` Field Renamed to `completed`

The boolean field `done` in the Task object has been renamed to `completed` for improved clarity. This affects both reading and updating task status.

### Before (v1)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false, // Old field name
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false, // New field name
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Code Example

**Before (v1) - Updating a task**

```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
task_id = 42
update_payload = {"done": True} # Using 'done'
response = requests.put(f"https://api.zrb.com/tasks/{task_id}", json=update_payload, headers=headers)
updated_task = response.json()
print(updated_task)
```

**After (v2) - Updating a task**

```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
update_payload = {"completed": True} # Using 'completed'
response = requests.put(f"https://api.zrb.com/v2/tasks/{task_id}", json=update_payload, headers=headers)
updated_task = response.json()
print(updated_task)
```

---

## 5. Task Creation Requires `project_id`

In v2, when creating a new task, the `project_id` field is now a required string in the request body. Omitting `project_id` will result in an HTTP 422 Unprocessable Entity error.

### Before (v1)

```json
{
  "title": "New task title"
}
```

### After (v2)

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### Code Example

**Before (v1) - Creating a task**

```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
new_task_payload = {"title": "Plan v2 migration"}
response = requests.post("https://api.zrb.com/tasks", json=new_task_payload, headers=headers)
created_task = response.json()
print(created_task)
```

**After (v2) - Creating a task**

```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
new_task_payload = {
    "title": "Plan v2 migration",
    "project_id": "proj_xyz456" # Required in v2
}
response = requests.post("https://api.zrb.com/v2/tasks", json=new_task_payload, headers=headers)
created_task = response.json()
print(created_task)
```

---

## 6. List Endpoints Return Paginated Data

All list endpoints (e.g., `GET /v2/tasks`) no longer return a bare array of items. Instead, they return a paginated envelope object that includes the `items` array, `total` count, and a `next_cursor` for pagination.

### Before (v1) - Response for `GET /tasks`

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2) - Response for `GET /v2/tasks`

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, you would pass `?cursor=<next_cursor>` as a query parameter. You can also specify a `limit` for the number of results per page (default 20).

### Code Example

**Before (v1) - Listing tasks**

```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
tasks = response.json() # Direct array of tasks
for task in tasks:
    print(f"Task ID: {task['id']}, Title: {task['title']}, Done: {task['done']}")
```

**After (v2) - Listing tasks**

```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
base_url = "https://api.zrb.com/v2/tasks"

# First page
response = requests.get(base_url, headers=headers)
tasks_data = response.json() # Paginated envelope
tasks = tasks_data["items"]
for task in tasks:
    print(f"Task ID: {task['id']}, Title: {task['title']}, Completed: {task['completed']}")

# Fetching the next page (if available)
next_cursor = tasks_data.get("next_cursor")
if next_cursor:
    print(f"\nFetching next page with cursor: {next_cursor}")
    response = requests.get(f"{base_url}?cursor={next_cursor}", headers=headers)
    next_page_data = response.json()
    next_page_tasks = next_page_data["items"]
    for task in next_page_tasks:
        print(f"Task ID: {task['id']}, Title: {task['title']}, Completed: {task['completed']}")
```

---

## 7. Migration Checklist

Use this checklist to ensure a smooth migration from Zrb CLI v1 to v2:

- [ ] **Update all API endpoint paths** to include the `/v2/` prefix (e.g., `/tasks` becomes `/v2/tasks`).
- [ ] **Change authentication header** from `X-Auth-Token: <api_key>` to `Authorization: Bearer <api_token>`. Ensure you are using a v2 compatible API token.
- [ ] **Update all references to Task IDs** from integers to UUID strings. This includes path parameters in GET, PUT, and DELETE requests.
- [ ] **Rename the `done` field to `completed`** in all Task object references, both when reading responses and constructing request bodies for updates.
- [ ] **Ensure `project_id` is included** in the request body when creating new tasks (`POST /v2/tasks`).
- [ ] **Modify logic for listing endpoints** to handle the new paginated envelope response structure. Access tasks via the `items` array and handle `next_cursor` for pagination.

---

## 8. Upgrade Command

To upgrade your Zrb CLI installation to v2, run the following command:

```bash
zrb upgrade --to v2
```