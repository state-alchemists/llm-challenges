# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary changes to migrate your applications from Zrb CLI v1 to v2. Version 2 introduces significant improvements, including project support and enhanced API consistency, but it also contains several breaking changes that require your attention.

## Breaking Changes

### 1. Endpoint Paths now require `/v2/` Prefix

All API endpoints in v2 are prefixed with `/v2/`. This means you need to update your base URL or endpoint paths to include this prefix for all Zrb API calls.

**Before (v1):**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

**Example:**
Before:
```python
import requests
response = requests.get("https://api.zrb.com/tasks", headers={"X-Auth-Token": "YOUR_V1_TOKEN"})
```

After:
```python
import requests
response = requests.get("https://api.zrb.com/v2/tasks", headers={"Authorization": "Bearer YOUR_V2_TOKEN"})
```

### 2. Authentication Header Changed

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported. All requests must now use a `Bearer` token in the `Authorization` header.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Example:**
Before:
```python
headers = {
    "X-Auth-Token": "YOUR_V1_TOKEN"
}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
```

After:
```python
headers = {
    "Authorization": "Bearer YOUR_V2_TOKEN"
}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
```

### 3. Task `id` Type Changed from Integer to UUID String

Task identifiers (`id`) are no longer integers. They are now UUID strings, which provides better global uniqueness and extensibility. This change impacts all operations that refer to a task by its ID.

**Before (v1 - integer ID):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2 - UUID string ID):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

**Example:**
Before:
```python
task_id = 42
response = requests.get(f"https://api.zrb.com/tasks/{task_id}", headers=headers)
```

After:
```python
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890" # Example UUID
response = requests.get(f"https://api.zrb.com/v2/tasks/{task_id}", headers=headers)
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. You must update your code to use the new field name when creating or updating tasks, and when processing task objects.

**Before (v1 - `done` field):**
```json
{
  "title": "Finish report",
  "done": true
}
```

**After (v2 - `completed` field):**
```json
{
  "title": "Finish report",
  "completed": true
}
```

**Example (Updating a task):**
Before:
```python
task_data = {"done": True}
response = requests.put(f"https://api.zrb.com/tasks/{task_id}", json=task_data, headers=headers)
```

After:
```python
task_data = {"completed": True}
response = requests.put(f"https://api.zrb.com/v2/tasks/{task_id}", json=task_data, headers=headers)
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, you must now specify the `project_id` to which the task belongs. This is a mandatory field for `POST /v2/tasks`. Omitting it will result in an HTTP 422 error.

**Before (v1 - no `project_id` required):**
```json
{
  "title": "New task title"
}
```

**After (v2 - `project_id` required):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Example (Creating a task):**
Before:
```python
new_task = {"title": "Submit expense report"}
response = requests.post("https://api.zrb.com/tasks", json=new_task, headers=headers)
```

After:
```python
new_task = {
    "title": "Submit expense report",
    "project_id": "proj_finance" # Example project ID
}
response = requests.post("https://api.zrb.com/v2/tasks", json=new_task, headers=headers)
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) no longer return a bare array of items. Instead, they return a paginated envelope object containing the `items` array, `total` count, and `next_cursor` for pagination.

**Before (v1 - bare array):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "..."},
  {"id": 2, "title": "Ship v1", "done": true, "..."}
]
```

**After (v2 - paginated envelope):**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_a", "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj_b", "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Example (Fetching tasks):**
Before:
```python
response = requests.get("https://api.zrb.com/tasks", headers=headers)
tasks = response.json()
for task in tasks:
    print(task["title"])
```

After:
```python
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
paginated_response = response.json()
tasks = paginated_response["items"]
for task in tasks:
    print(task["title"])
# To fetch next page:
# next_cursor = paginated_response.get("next_cursor")
# if next_cursor:
#     response = requests.get(f"https://api.zrb.com/v2/tasks?cursor={next_cursor}", headers=headers)
```

## Migration Checklist

To successfully migrate your Zrb CLI v1 application to v2, follow these steps:

1.  [ ] **Update CLI to v2:** Run the upgrade command.
2.  [ ] **Adjust Endpoint Paths:** Prefix all Zrb API calls with `/v2/`.
3.  [ ] **Change Authentication Header:** Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>`.
4.  [ ] **Migrate Task IDs:** Update any stored task IDs from integers to UUID strings. Ensure your application can handle UUIDs for task identification in requests and responses.
5.  [ ] **Rename Task Completion Field:** Change all references to the `done` field to `completed` in your code, including when creating, updating, or reading tasks.
6.  [ ] **Provide `project_id` for Task Creation:** When creating new tasks (`POST /v2/tasks`), ensure you include a valid `project_id` in the request body.
7.  [ ] **Update List Endpoint Processing:** Modify your code to expect and parse the paginated envelope structure for all list operations. Access task items from the `items` array within the response.
8.  [ ] **Implement Pagination (Optional but Recommended):** Leverage the `cursor` and `next_cursor` fields for efficient pagination on list endpoints.
9.  [ ] **Test Thoroughly:** After making all changes, thoroughly test your application to ensure full compatibility with Zrb CLI v2.

## Upgrade Command

To upgrade your Zrb CLI to the latest v2 version, run the following command:

```bash
zrb upgrade --to v2
```
