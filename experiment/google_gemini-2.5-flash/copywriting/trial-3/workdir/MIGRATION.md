# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary changes to migrate your existing Zrb CLI v1 integrations to the new v2 API. Zrb CLI v2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication. Please review all breaking changes carefully.

## Breaking Changes

### 1. API Endpoint Prefix Change

All API endpoints are now prefixed with `/v2/`. You must update all your endpoint URLs accordingly.

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

**Example (List Tasks):**

**Before (v1):**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
tasks = response.json()
print(tasks)
```

**After (v2):**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
paginated_response = response.json()
tasks = paginated_response["items"] # Note: response is now paginated
print(tasks)
```

### 2. Authentication Header Changed

The authentication mechanism has changed from a custom `X-Auth-Token` header to a standard `Authorization: Bearer` token. Requests using the old header will receive an HTTP 401 Unauthorized error.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Example:**

**Before (v1):**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
```

**After (v2):**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
```

### 3. Task `id` Type Changed

The `id` field for Task objects, previously an integer, is now a UUID string. This affects all endpoints that reference a task by its ID.

**Before (v1 - Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2 - Task Object):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

**Example (Get Task):**

**Before (v1):**
```python
import requests

task_id = 42 # Integer ID
headers = {"X-Auth-Token": "your_v1_api_key"}
response = requests.get(f"https://api.zrb.com/tasks/{task_id}", headers=headers)
task = response.json()
print(task)
```

**After (v2):**
```python
import requests

task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890" # UUID string ID
headers = {"Authorization": "Bearer your_v2_api_token"}
response = requests.get(f"https://api.zrb.com/v2/tasks/{task_id}", headers=headers)
task = response.json()
print(task)
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. This change impacts the Task object structure and the request body for updating tasks.

**Before (v1 - Task Object):**
```json
{
  "id": 42,
  "title": "Ship v1",
  "done": true
}
```

**After (v2 - Task Object):**
```json
{
  "id": "...",
  "title": "Ship v1",
  "completed": true
}
```

**Example (Update Task):**

**Before (v1):**
```python
import requests

task_id = 1
headers = {"X-Auth-Token": "your_v1_api_key"}
payload = {"done": True} # Using 'done'
response = requests.put(f"https://api.zrb.com/tasks/{task_id}", json=payload, headers=headers)
updated_task = response.json()
print(updated_task)
```

**After (v2):**
```python
import requests

task_id = "..."
headers = {"Authorization": "Bearer your_v2_api_token"}
payload = {"completed": True} # Using 'completed'
response = requests.put(f"https://api.zrb.com/v2/tasks/{task_id}", json=payload, headers=headers)
updated_task = response.json()
print(updated_task)
```

### 5. Task Creation Now Requires `project_id`

When creating new tasks, the `project_id` field is now mandatory in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

**Before (v1 - Create Task):**
```json
{
  "title": "New task title"
}
```

**After (v2 - Create Task):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Example (Create Task):**

**Before (v1):**
```python
import requests

headers = {"X-Auth-Token": "your_v1_api_key"}
payload = {"title": "Refactor authentication"}
response = requests.post("https://api.zrb.com/tasks", json=payload, headers=headers)
new_task = response.json()
print(new_task)
```

**After (v2):**
```python
import requests

headers = {"Authorization": "Bearer your_v2_api_token"}
payload = {
  "title": "Refactor authentication",
  "project_id": "proj_dev_team" # project_id is now required
}
response = requests.post("https://api.zrb.com/v2/tasks", json=payload, headers=headers)
new_task = response.json()
print(new_task)
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints, such as `GET /v2/tasks`, now return a paginated response wrapped in an envelope object, instead of a bare array. The envelope includes `items`, `total`, and `next_cursor` fields.

**Before (v1 - List Tasks Response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "..."},
  {"id": 2, "title": "Ship v1", "done": true, "..."}
]
```

**After (v2 - List Tasks Response):**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Example (List Tasks - Accessing Items and Pagination):**

**Before (v1):**
```python
import requests

headers = {"X-Auth-Token": "your_v1_api_key"}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
tasks = response.json() # Direct array
for task in tasks:
    print(task["title"])
```

**After (v2):**
```python
import requests

headers = {"Authorization": "Bearer your_v2_api_token"}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
paginated_response = response.json() # Paginated envelope
tasks = paginated_response["items"]
total_tasks = paginated_response["total"]
next_cursor = paginated_response["next_cursor"]

for task in tasks:
    print(task["title"])

# To fetch the next page:
if next_cursor:
    next_page_response = requests.get(f"https://api.zrb.com/v2/tasks?cursor={next_cursor}", headers=headers)
    # Process next_page_response...
```

## Migration Checklist

To successfully migrate your Zrb CLI integrations to v2, follow these steps:

1.  **Update API Base URLs**: Change all endpoint paths from `/tasks` to `/v2/tasks` (and similar for other resources if applicable).
2.  **Revise Authentication**: Replace `X-Auth-Token` headers with `Authorization: Bearer <your_api_token>`. Ensure you have obtained a v2 compatible API token.
3.  **Adjust Task ID Handling**: Update any code that uses task IDs to expect and provide UUID strings instead of integers.
4.  **Rename `done` to `completed`**: Update all references to the `done` field in Task objects and update requests (especially for `PUT /v2/tasks/{id}`) to use `completed`.
5.  **Add `project_id` to Task Creation**: Modify all `POST /v2/tasks` requests to include a `project_id` in the request body.
6.  **Handle Paginated Responses**: Update code that consumes list endpoints (`GET /v2/tasks`) to parse the new paginated envelope structure (accessing `items` from the response and handling `total` and `next_cursor` for pagination).

## Upgrade Command

To upgrade your Zrb CLI client to the latest version, run:

```bash
zrb upgrade --version v2
```