# Zrb CLI API v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI API v2 and provides a step-by-step process for migrating your existing v1 integrations. Version 2 brings new features like project management and improved pagination, alongside significant changes to authentication and core data structures.

## Summary of Breaking Changes

The following changes require updates to your existing v1 code:

1.  **API Endpoint Paths**: All API endpoints are now prefixed with `/v2/`.
2.  **Authentication Header**: The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer`.
3.  **Task ID Type**: The `id` field for Task objects has changed from an integer to a UUID string.
4.  **Task Field Renamed**: The `done` field in the Task object has been renamed to `completed`.
5.  **Project ID Requirement for Task Creation**: Creating a task (`POST /v2/tasks`) now requires a `project_id`.
6.  **Paginated List Responses**: All list endpoints now return a paginated envelope object instead of a bare array of items.

## Detailed Breaking Changes and Migration Examples

### 1. API Endpoint Paths

All API requests must now include `/v2/` in their paths.

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
# v1 (Python requests example)
import requests
api_key = "YOUR_V1_API_KEY"
headers = {"X-Auth-Token": api_key}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
tasks = response.json()
```

```python
# v2 (Python requests example)
import requests
api_token = "YOUR_V2_API_TOKEN" # Note: This is now a token, not just an API key
headers = {"Authorization": f"Bearer {api_token}"}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
# Note: Response is now a paginated envelope
paginated_response = response.json()
tasks = paginated_response["items"]
```

### 2. Authentication Header

The authentication mechanism has been updated to use a Bearer token in the `Authorization` header. Requests using `X-Auth-Token` will now result in an HTTP 401 Unauthorized error.

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
// v1 (JavaScript fetch example)
const apiKey = "YOUR_V1_API_KEY";
fetch("https://api.zrb.com/tasks", {
  headers: {
    "X-Auth-Token": apiKey
  }
});
```

```python
// v2 (JavaScript fetch example)
const apiToken = "YOUR_V2_API_TOKEN";
fetch("https://api.zrb.com/v2/tasks", {
  headers: {
    "Authorization": `Bearer ${apiToken}`
  }
});
```

### 3. Task ID Type

The `id` field in the `Task` object has transitioned from an integer to a UUID string. This affects all endpoints that involve task IDs (Get, Update, Delete).

**Before (v1 Task Object):**
```json
{
  "id": 42,
  "title": "Old task",
  "done": false
}
```

**After (v2 Task Object):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "New task",
  "completed": false,
  "project_id": "proj_abc123"
}
```

**Migration Example (Get Task):**

```python
# v1
task_id_v1 = 42
response = requests.get(f"https://api.zrb.com/tasks/{task_id_v1}", headers=headers)
```

```python
# v2
task_id_v2 = "a1b2c3d4-e5f6-7890-abcd-ef1234567890" # Must be a UUID string
response = requests.get(f"https://api.zrb.com/v2/tasks/{task_id_v2}", headers=headers)
```

### 4. Task Field Renamed: `done` to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. This impacts `Task` object representations in responses and `Update Task` requests.

**Before (v1 Update Task request body):**
```json
{
  "done": true
}
```

**After (v2 Update Task request body):**
```json
{
  "completed": true
}
```

**Migration Example (Update Task Status):**

```python
# v1
task_id = 42
data = {"done": True}
response = requests.put(f"https://api.zrb.com/tasks/{task_id}", headers=headers, json=data)
```

```python
# v2
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
data = {"completed": True} # Use "completed" instead of "done"
response = requests.put(f"https://api.zrb.com/v2/tasks/{task_id}", headers=headers, json=data)
```

### 5. Task Creation Requires `project_id`

When creating new tasks via `POST /v2/tasks`, a `project_id` is now a mandatory field in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

**Before (v1 Create Task request body):**
```json
{
  "title": "New task title"
}
```

**After (v2 Create Task request body):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Migration Example (Create Task):**

```python
# v1
data = {"title": "Design new UI"}
response = requests.post("https://api.zrb.com/tasks", headers=headers, json=data)
```

```python
# v2
data = {
  "title": "Design new UI",
  "project_id": "design-team-project" # project_id is now required
}
response = requests.post("https://api.zrb.com/v2/tasks", headers=headers, json=data)
```

### 6. Paginated List Responses

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope object instead of a direct array of items. This envelope includes `items`, `total`, and `next_cursor` fields.

**Before (v1 List Tasks response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 List Tasks response):**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "p1", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "p1", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, you pass the `next_cursor` as a query parameter: `GET /v2/tasks?cursor=cursor_xyz`.

**Migration Example (Processing List Responses):**

```python
# v1
response = requests.get("https://api.zrb.com/tasks", headers=headers)
tasks = response.json() # tasks is a list
for task in tasks:
    print(f"Task: {task['title']}, Done: {task['done']}")
```

```python
# v2
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
paginated_response = response.json() # response is an object
tasks = paginated_response["items"] # items is the list of tasks
next_cursor = paginated_response["next_cursor"] # for next page

for task in tasks:
    print(f"Task: {task['title']}, Completed: {task['completed']}") # Use 'completed'
```

## Migration Checklist

To successfully upgrade your Zrb CLI API integration from v1 to v2:

1.  [ ] **Update API Endpoint Paths**: Prefix all Zrb API endpoint URLs with `/v2/`.
2.  [ ] **Switch Authentication**:
    *   Obtain a new v2 API token.
    *   Change your `X-Auth-Token` header to `Authorization: Bearer <your_api_token>`.
3.  [ ] **Adjust Task ID Handling**: Update all code that uses task IDs to expect and handle UUID strings instead of integers.
4.  [ ] **Rename Task Completion Field**: Replace all references to the `done` field with `completed` in your code, both when reading task objects and when sending update requests.
5.  [ ] **Add `project_id` for Task Creation**: Ensure that all `POST /v2/tasks` requests include a `project_id` in the request body.
6.  [ ] **Adapt to Paginated List Responses**: Modify code that consumes list endpoint responses to extract items from the `items` field of the paginated envelope object. Implement logic for handling pagination using `next_cursor` if needed.

## Upgrade Command

To upgrade your Zrb CLI, run the following command (assuming a typical npm package setup):

```bash
npm install -g zrb@latest
```
