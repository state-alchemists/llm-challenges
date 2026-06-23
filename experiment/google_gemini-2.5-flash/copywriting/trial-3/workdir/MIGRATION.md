# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes and new features in Zrb CLI v2, providing step-by-step instructions and code examples to help you migrate your existing applications.

## What's New in v2

Zrb CLI v2 introduces significant enhancements, including:

*   **Projects**: Organize your tasks into projects for better management.
*   **Improved Pagination**: All list endpoints now provide standardized pagination for efficient data retrieval.
*   **Stricter Authentication**: Enhanced security with Bearer token authentication.
*   **UUID Task IDs**: Task IDs are now globally unique UUID strings, offering more robust identification.

These changes bring a more scalable and consistent API experience.

## Breaking Changes

Below are the breaking changes you need to address when migrating from Zrb CLI v1 to v2.

### 1. All Endpoints are Now Prefixed with `/v2/`

All API endpoints in v2 are now prefixed with `/v2/`. This ensures versioning and allows for future API evolution.

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

**Example:** Fetching a task in v1 vs v2.

```python
# v1
import requests
response = requests.get("https://api.zrb.com/tasks/123", headers={"X-Auth-Token": "YOUR_V1_TOKEN"})

# v2
import requests
response = requests.get("https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890", headers={"Authorization": "Bearer YOUR_V2_TOKEN"})
```

### 2. Authentication Header Changed

The authentication header has been updated from `X-Auth-Token` to a standard `Authorization: Bearer` token. Requests using the old header will receive an HTTP 401 Unauthorized response.

**Before (v1):**

```http
X-Auth-Token: <your_api_key>
```

**After (v2):**

```http
Authorization: Bearer <your_api_token>
```

**Example:** Authenticating a request.

```python
# v1
headers = {
    "X-Auth-Token": "YOUR_V1_API_KEY"
}
# requests.get("https://api.zrb.com/tasks", headers=headers)

# v2
headers = {
    "Authorization": "Bearer YOUR_V2_API_TOKEN"
}
# requests.get("https://api.zrb.com/v2/tasks", headers=headers)
```

### 3. Task `id` Type Changed from Integer to UUID String

Task identifiers are now UUID strings instead of integers. This change affects how you store, retrieve, and reference tasks.

**Before (v1) Task Object:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) Task Object:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Example:** Referencing a task by ID.

```python
# v1 (integer ID)
task_id_v1 = 42
# requests.get(f"https://api.zrb.com/tasks/{task_id_v1}", headers=v1_headers)

# v2 (UUID string ID)
task_id_v2 = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
# requests.get(f"https://api.zrb.com/v2/tasks/{task_id_v2}", headers=v2_headers)
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`.

**Before (v1) Request Body for Update:**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) Request Body for Update:**

```json
{
  "title": "Updated title",
  "completed": true
}
```

**Example:** Updating a task's status.

```python
# v1
update_payload_v1 = {
    "title": "Complete documentation",
    "done": True
}
# requests.put(f"https://api.zrb.com/tasks/{task_id_v1}", json=update_payload_v1, headers=v1_headers)

# v2
update_payload_v2 = {
    "title": "Complete documentation",
    "completed": True
}
# requests.put(f"https://api.zrb.com/v2/tasks/{task_id_v2}", json=update_payload_v2, headers=v2_headers)
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, the `project_id` field is now mandatory. Omitting it will result in an HTTP 422 Unprocessable Entity response.

**Before (v1) Request Body for Create:**

```json
{
  "title": "New task title"
}
```

**After (v2) Request Body for Create:**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Example:** Creating a new task.

```python
# v1
create_payload_v1 = {
    "title": "Review PR"
}
# requests.post("https://api.zrb.com/tasks", json=create_payload_v1, headers=v1_headers)

# v2
create_payload_v2 = {
    "title": "Review PR",
    "project_id": "dev_team_proj_456" # A valid project ID is now required
}
# requests.post("https://api.zrb.com/v2/tasks", json=create_payload_v2, headers=v2_headers)
```

### 6. List Endpoints Return a Paginated Envelope Instead of a Bare Array

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response envelope instead of a bare array of items. The envelope includes `items`, `total`, and `next_cursor` for navigating results.

**Before (v1) List Tasks Response:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) List Tasks Response:**

```json
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "c3d4...", "title": "Ship v2", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Example:** Processing a list of tasks.

```python
# v1
response_v1 = requests.get("https://api.zrb.com/tasks", headers=v1_headers).json()
for task in response_v1:
    print(f"Task: {task['title']}, Done: {task['done']}")

# v2
response_v2 = requests.get("https://api.zrb.com/v2/tasks", headers=v2_headers).json()
for task in response_v2["items"]:
    print(f"Task: {task['title']}, Completed: {task['completed']}, Project: {task['project_id']}")

# To fetch the next page in v2
# next_page_cursor = response_v2["next_cursor"]
# if next_page_cursor:
#     next_page_response = requests.get(f"https://api.zrb.com/v2/tasks?cursor={next_page_cursor}", headers=v2_headers).json()
```

## Migration Checklist

Follow these steps to successfully migrate your Zrb CLI v1 application to v2:

1.  **Update Zrb CLI**: Ensure your local Zrb CLI installation is updated to v2.
    ```bash
    # Assuming zrb is a Python package, use pip
    pip install --upgrade zrb
    # Or your specific package manager command
    ```
2.  **Update Authentication**: Change your API key handling to use the `Authorization: Bearer` header.
3.  **Adjust Endpoint Paths**: Prefix all Zrb API endpoint calls with `/v2/`.
4.  **Handle Task ID Type**: Update your code to expect and work with UUID strings for task IDs instead of integers. This might involve changes to database schemas if you were storing Zrb task IDs.
5.  **Rename `done` field**: Replace all occurrences of the `done` field with `completed` in your task objects and API request bodies.
6.  **Add `project_id` to Task Creation**: Modify your task creation logic to include a `project_id` in the request body. Ensure you have valid project IDs available.
7.  **Adapt to Paginated List Responses**: Update code that consumes list endpoints to parse the new paginated envelope structure, accessing items via the `items` key and handling `next_cursor` for pagination.
8.  **Test Your Application**: Thoroughly test all API interactions in your application to ensure full compatibility with Zrb CLI v2.

## Upgrade Command

To upgrade your Zrb CLI, run the following command in your terminal:

```bash
zrb upgrade --to v2
```
