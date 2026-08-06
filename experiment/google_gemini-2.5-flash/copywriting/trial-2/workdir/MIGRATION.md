# Zrb CLI v1 to v2 Migration Guide

This guide outlines the breaking changes introduced in Zrb CLI v2 and provides a step-by-step process to migrate your existing v1 applications. Zrb CLI v2 focuses on improving scalability and consistency, introducing project-based task management, enhanced authentication, and standardized API responses.

## Breaking Changes

### 1. All Endpoints are now prefixed with `/v2/`

All API endpoints have moved under the `/v2/` path prefix. Requests to v1 endpoints will no longer be routed correctly.

**Before (v1):**
```
GET /tasks
POST /tasks
GET /tasks/{id}
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
```

**Migration Example (List Tasks):**

```python
# v1
import requests
response = requests.get("https://api.zrb.com/tasks", headers={"X-Auth-Token": "YOUR_V1_TOKEN"})
print(response.json())

# v2
import requests
response = requests.get("https://api.zrb.com/v2/tasks", headers={"Authorization": "Bearer YOUR_V2_TOKEN"})
print(response.json())
```

### 2. Authentication Header Changed

The authentication mechanism has been updated from a custom `X-Auth-Token` header to a standard `Authorization: Bearer` token. Requests using the old header will result in an HTTP 401 Unauthorized error.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Migration Example:**

```python
# v1
headers = {
    "X-Auth-Token": "YOUR_V1_TOKEN"
}
# requests.get("https://api.zrb.com/tasks", headers=headers)

# v2
headers = {
    "Authorization": "Bearer YOUR_V2_TOKEN"
}
# requests.get("https://api.zrb.com/v2/tasks", headers=headers)
```

### 3. Task `id` Type Changed from Integer to UUID String

Task identifiers (`id`) are now universally unique identifiers (UUIDs) represented as strings, instead of integers. This impacts all endpoints that reference tasks by their ID.

**Before (v1) - Task Object:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) - Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Migration Example (Get Task):**

```python
# v1
task_id_v1 = 42
# response = requests.get(f"https://api.zrb.com/tasks/{task_id_v1}", headers=headers)

# v2
task_id_v2 = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
# response = requests.get(f"https://api.zrb.com/v2/tasks/{task_id_v2}", headers=headers)
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`.

**Before (v1):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

**Migration Example (Update Task):**

```python
# v1
task_data_v1 = {
    "title": "Updated title v1",
    "done": True
}
# requests.put(f"https://api.zrb.com/tasks/{task_id_v1}", json=task_data_v1, headers=headers)

# v2
task_data_v2 = {
    "title": "Updated title v2",
    "completed": True
}
# requests.put(f"https://api.zrb.com/v2/tasks/{task_id_v2}", json=task_data_v2, headers=headers)
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, the `project_id` field is now mandatory. This associates tasks with a specific project context within Zrb CLI v2. Omitting this field will result in an HTTP 422 Unprocessable Entity error.

**Before (v1) - Create Task Request Body:**
```json
{
  "title": "New task title"
}
```

**After (v2) - Create Task Request Body:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Migration Example (Create Task):**

```python
# v1
new_task_v1 = {
    "title": "Plan v2 migration"
}
# requests.post("https://api.zrb.com/tasks", json=new_task_v1, headers=headers)

# v2
new_task_v2 = {
    "title": "Update documentation",
    "project_id": "proj_docs_team"
}
# requests.post("https://api.zrb.com/v2/tasks", json=new_task_v2, headers=headers)
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response wrapped in an envelope object, rather than a bare array of items. This change supports efficient retrieval of large datasets.

**Before (v1) - List Tasks Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) - List Tasks Response (Paginated Envelope):**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_home", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj_dev", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```
To fetch the next page, use the `next_cursor` value as a query parameter: `GET /v2/tasks?cursor=cursor_xyz`.

**Migration Example (List Tasks with Pagination):**

```python
# v1
# response = requests.get("https://api.zrb.com/tasks", headers=headers)
# tasks = response.json()
# for task in tasks:
#     print(f"Task ID: {task['id']}, Title: {task['title']}")

# v2
# response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
# paginated_response = response.json()
# tasks = paginated_response["items"]
# next_cursor = paginated_response.get("next_cursor")

# for task in tasks:
#     print(f"Task ID: {task['id']}, Title: {task['title']}")

# if next_cursor:
#     print(f"Next page available with cursor: {next_cursor}")
```

## Migration Checklist

To successfully upgrade your Zrb CLI integration to v2:

1.  **Update API Endpoints:** Change all `/tasks` endpoint paths to `/v2/tasks`.
2.  **Migrate Authentication:**
    *   Generate a new v2 API token.
    *   Update your authentication header from `X-Auth-Token: <key>` to `Authorization: Bearer <token>`.
3.  **Adjust Task ID Handling:** Modify code that stores or references task IDs to expect and handle UUID strings instead of integers.
4.  **Rename `done` to `completed`:** Update all references to the task completion status field from `done` to `completed` in request bodies and response parsing.
5.  **Add `project_id` to Task Creation:** Ensure all task creation requests include a valid `project_id` in the request body.
6.  **Handle Paginated Responses:** Update code that processes list endpoint responses to parse the `items` array from the new paginated envelope and handle `total` and `next_cursor` for pagination.

## Upgrade Command

To upgrade your Zrb CLI:

```bash
zrb upgrade --to v2
```
