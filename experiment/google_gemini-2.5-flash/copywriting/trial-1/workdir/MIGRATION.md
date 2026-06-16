# Zrb CLI v1 to v2 Migration Guide

Zrb CLI v2 introduces significant enhancements, including project management, improved pagination, and a more robust authentication mechanism. This guide will walk you through the necessary changes to migrate your existing v1 integrations to v2.

## Breaking Changes Summary

Here's a quick overview of the breaking changes you'll encounter:

1.  **Endpoint Prefix**: All API endpoints are now prefixed with `/v2/`.
2.  **Authentication Header**: The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer`.
3.  **Task ID Type**: Task `id` has changed from an integer to a UUID string.
4.  **Field Rename**: The `done` field on Task objects has been renamed to `completed`.
5.  **Required Field for Creation**: Task creation (`POST /v2/tasks`) now requires a `project_id`.
6.  **Paginated Lists**: List endpoints now return a paginated envelope instead of a bare array of items.

---

## Detailed Breaking Changes and Migration Steps

### 1. Endpoint Prefix Change: `/tasks` to `/v2/tasks`

All API endpoints now include a `/v2/` prefix. You must update your API request paths accordingly.

**Before (v1):**
```
GET /tasks
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

**Migration Example:**

**v1 Code (Python with `requests`):**
```python
import requests

api_key = "YOUR_V1_API_KEY"
base_url = "https://api.zrb.com" # Example base URL

# List tasks
response = requests.get(f"{base_url}/tasks", headers={"X-Auth-Token": api_key})
tasks = response.json()
print(tasks)
```

**v2 Code (Python with `requests`):**
```python
import requests

api_token = "YOUR_V2_API_TOKEN"
base_url = "https://api.zrb.com" # Example base URL

# List tasks
response = requests.get(
    f"{base_url}/v2/tasks",
    headers={"Authorization": f"Bearer {api_token}"}
)
# Note: response structure changes due to pagination (see below)
paginated_response = response.json()
print(paginated_response["items"])
```

### 2. Authentication Header Change

The authentication mechanism has been updated for better security and standardization.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```
Requests using the old `X-Auth-Token` header will now result in an HTTP 401 Unauthorized error.

**Migration Example:**

**v1 Code:**
```python
headers = {
    "X-Auth-Token": "YOUR_V1_API_KEY"
}
```

**v2 Code:**
```python
headers = {
    "Authorization": "Bearer YOUR_V2_API_TOKEN"
}
```

### 3. Task `id` Type Changed from Integer to UUID String

Task identifiers are now UUID strings instead of sequential integers. This impacts how you store, retrieve, and reference tasks.

**Before (v1 Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 Task Object):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Migration Example:**

**v1 Code (referencing a task by ID):**
```python
task_id = 42
response = requests.get(f"{base_url}/tasks/{task_id}", headers=v1_headers)
task = response.json()
print(f"Task title: {task['title']}")
```

**v2 Code (referencing a task by ID):**
```python
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890" # Example UUID
response = requests.get(f"{base_url}/v2/tasks/{task_id}", headers=v2_headers)
task = response.json()
print(f"Task title: {task['title']}")
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed.

**Before (v1):**
```json
{
  "done": true
}
```

**After (v2):**
```json
{
  "completed": true
}
```

**Migration Example (Updating a Task):**

**v1 Code:**
```python
task_id = 42
update_payload = {"done": True}
response = requests.put(f"{base_url}/tasks/{task_id}", json=update_payload, headers=v1_headers)
updated_task = response.json()
print(f"Task {updated_task['id']} done status: {updated_task['done']}")
```

**v2 Code:**
```python
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
update_payload = {"completed": True}
response = requests.put(f"{base_url}/v2/tasks/{task_id}", json=update_payload, headers=v2_headers)
updated_task = response.json()
print(f"Task {updated_task['id']} completed status: {updated_task['completed']}")
```

### 5. Task Creation Now Requires `project_id`

Tasks are now associated with projects. When creating a new task, you must specify the `project_id`.

**Before (v1 `POST /tasks` Request Body):**
```json
{
  "title": "New task title"
}
```

**After (v2 `POST /v2/tasks` Request Body):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```
Omitting `project_id` in v2 will result in an HTTP 422 Unprocessable Entity error.

**Migration Example (Creating a Task):**

**v1 Code:**
```python
create_payload = {"title": "My new v1 task"}
response = requests.post(f"{base_url}/tasks", json=create_payload, headers=v1_headers)
new_task = response.json()
print(f"Created task: {new_task['title']} (ID: {new_task['id']})")
```

**v2 Code:**
```python
project_id = "proj_abc123" # Replace with an actual project ID
create_payload = {"title": "My new v2 task", "project_id": project_id}
response = requests.post(f"{base_url}/v2/tasks", json=create_payload, headers=v2_headers)
new_task = response.json()
print(f"Created task: {new_task['title']} (ID: {new_task['id']}, Project: {new_task['project_id']})")
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (`GET /v2/tasks`) now return a standardized paginated response envelope, rather than a direct array of items.

**Before (v1 `GET /tasks` Response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "..."},
  {"id": 2, "title": "Ship v1", "done": true, "..."}
]
```

**After (v2 `GET /v2/tasks` Response):**
```json
{
  "items": [
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "..."},
    {"id": "uuid2", "title": "Ship v2", "completed": true, "project_id": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
You will need to access the `items` key to get the list of resources. Pagination can be controlled with `cursor` and `limit` query parameters.

**Migration Example (Listing Tasks):**

**v1 Code:**
```python
response = requests.get(f"{base_url}/tasks", headers=v1_headers)
tasks = response.json()
for task in tasks:
    print(f"- {task['title']}")
```

**v2 Code:**
```python
response = requests.get(f"{base_url}/v2/tasks", headers=v2_headers, params={"limit": 5})
paginated_data = response.json()
tasks = paginated_data["items"]
for task in tasks:
    print(f"- {task['title']}")

# To fetch the next page
if paginated_data.get("next_cursor"):
    next_cursor = paginated_data["next_cursor"]
    response = requests.get(f"{base_url}/v2/tasks", headers=v2_headers, params={"cursor": next_cursor, "limit": 5})
    # ... process next page
```

---

## Migration Checklist

To ensure a smooth transition to Zrb CLI v2, follow these steps:

1.  [ ] **Update CLI Installation**: Ensure your Zrb CLI is updated to v2.
2.  [ ] **Review Authentication**: Obtain a new v2 API token if necessary, and update all `X-Auth-Token` headers to `Authorization: Bearer <your_api_token>`.
3.  [ ] **Adjust Endpoint Paths**: Prefix all Zrb API endpoint calls with `/v2/`.
4.  [ ] **Refactor Task IDs**: Update any code that stores, parses, or expects integer `id` values to handle UUID strings instead.
5.  [ ] **Rename Task Fields**: Change all references to the `done` field on Task objects to `completed`.
6.  [ ] **Add `project_id` for Task Creation**: Modify `POST /v2/tasks` requests to include a `project_id` in the request body.
7.  [ ] **Handle Paginated Responses**: Adapt code that consumes list endpoint responses to parse the `items` array from the new paginated envelope structure. Implement cursor-based pagination if required.
8.  [ ] **Thoroughly Test**: Run your automated tests and manually verify all Zrb CLI integrations after migration.

---

## Upgrade Command

To upgrade your Zrb CLI to the latest v2 version, run:

```bash
zrb upgrade --to v2
```
