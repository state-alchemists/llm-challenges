# Zrb CLI v1 to v2 Migration Guide

Zrb CLI v2 is a significant evolution, introducing new features like project management and improved pagination, alongside important changes to enhance security and consistency. This guide details the breaking changes from v1 to v2 and provides clear steps for migrating your existing integrations.

## What's New and Why Upgrade?

Zrb CLI v2 brings:
*   **Project Context**: Tasks are now associated with projects, allowing for better organization and filtering.
*   **Improved Pagination**: List endpoints now use a consistent, cursor-based pagination model for more efficient data retrieval.
*   **Stricter Authentication**: Enhanced security with standard Bearer token authentication.

Upgrading ensures you can leverage these new capabilities and maintain compatibility with the latest Zrb ecosystem.

## Breaking Changes

This section outlines every breaking change and provides "before" and "after" code examples to guide your migration.

### 1. Endpoint Prefix Change

All API endpoints now include a `/v2/` prefix.

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

**Example:** Fetching all tasks.

```bash
# v1: List all tasks
curl -H "X-Auth-Token: <your_api_key>" \
     http://localhost:8080/tasks
```

```bash
# v2: List all tasks
curl -H "Authorization: Bearer <your_api_token>" \
     http://localhost:8080/v2/tasks
```

### 2. Authentication Header Changed

The authentication mechanism has been updated to use a standard `Authorization: Bearer` token. Requests using the old `X-Auth-Token` header will result in an HTTP 401 Unauthorized response.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Example:** Authenticating a request.

```python
# v1: Python example using requests
import requests
headers = {"X-Auth-Token": "YOUR_V1_API_KEY"}
response = requests.get("http://localhost:8080/tasks", headers=headers)
```

```python
# v2: Python example using requests
import requests
headers = {"Authorization": "Bearer YOUR_V2_API_TOKEN"}
response = requests.get("http://localhost:8080/v2/tasks", headers=headers)
```

### 3. Task `id` Type Changed

The `id` field for Task objects has changed from an integer to a UUID string. This affects all endpoints that take an `id` as a path parameter, such as `GET /tasks/{id}`, `PUT /tasks/{id}`, and `DELETE /tasks/{id}`.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

**Example:** Retrieving a specific task.

```bash
# v1: Get task with integer ID
curl -H "X-Auth-Token: <your_api_key>" \
     http://localhost:8080/tasks/42
```

```bash
# v2: Get task with UUID string ID
curl -H "Authorization: Bearer <your_api_token>" \
     http://localhost:8080/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. You must update your request and response parsing accordingly.

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

**Example:** Updating a task's status.

```python
# v1: Mark a task as done
import requests
headers = {"X-Auth-Token": "YOUR_V1_API_KEY"}
data = {"done": True}
response = requests.put("http://localhost:8080/tasks/42", headers=headers, json=data)
```

```python
# v2: Mark a task as completed
import requests
headers = {"Authorization": "Bearer YOUR_V2_API_TOKEN"}
data = {"completed": True}
response = requests.put("http://localhost:8080/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890", headers=headers, json=data)
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, the `project_id` field is now mandatory. Omitting it will result in an HTTP 422 Unprocessable Entity error.

**Before (v1):**
```json
{
  "title": "New task title"
}
```

**After (v2):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Example:** Creating a new task.

```bash
# v1: Create a task
curl -X POST -H "X-Auth-Token: <your_api_key>" \
     -H "Content-Type: application/json" \
     -d '{"title": "Prepare presentation"}' \
     http://localhost:8080/tasks
```

```bash
# v2: Create a task with a project ID
curl -X POST -H "Authorization: Bearer <your_api_token>" \
     -H "Content-Type: application/json" \
     -d '{"title": "Prepare presentation", "project_id": "proj_dev_team"}' \
     http://localhost:8080/v2/tasks
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) no longer return a bare array. Instead, they return a paginated envelope object containing the `items` array, `total` count, and a `next_cursor` for pagination.

**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
```json
{
  "items": [
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid2", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To access the task items, you will need to reference the `items` key in the response object. To fetch subsequent pages, use the `next_cursor` query parameter.

**Example:** Accessing listed tasks and pagination.

```python
# v1: Process list response
response_data = requests.get("http://localhost:8080/tasks", headers=v1_headers).json()
for task in response_data:
    print(f"Task ID: {task['id']}, Title: {task['title']}")
```

```python
# v2: Process list response with pagination
response_data = requests.get("http://localhost:8080/v2/tasks", headers=v2_headers).json()
for task in response_data['items']: # Access items from the envelope
    print(f"Task ID: {task['id']}, Title: {task['title']}")

# To get the next page
if response_data.get('next_cursor'):
    next_page_response = requests.get(f"http://localhost:8080/v2/tasks?cursor={response_data['next_cursor']}", headers=v2_headers).json()
```

## Migration Checklist

Follow these steps to migrate your Zrb CLI integrations to v2:

1.  [ ] **Update CLI:** Upgrade your Zrb CLI installation to v2.
2.  [ ] **API Base Paths:** Change all API endpoint calls from `/tasks` to `/v2/tasks`.
3.  [ ] **Authentication:** Replace `X-Auth-Token` headers with `Authorization: Bearer <your_api_token>`.
4.  [ ] **Task IDs:** Update any logic that stores or uses task IDs to expect and handle UUID strings instead of integers.
5.  [ ] **Task Completion Field:** Rename all references to the `done` field to `completed` in your code.
6.  [ ] **Task Creation:** Modify task creation requests to include a `project_id`.
7.  [ ] **List Endpoint Parsing:** Adjust code that processes list endpoint responses to access the task data via the `items` key of the paginated envelope.
8.  [ ] **Pagination Logic:** Implement or update pagination logic to use the `cursor` and `next_cursor` parameters for fetching subsequent pages.
9.  [ ] **Testing:** Thoroughly test your updated integrations against the v2 API.

## Upgrade Command

To upgrade your Zrb CLI installation, run:

```bash
zrb upgrade --to v2
```
