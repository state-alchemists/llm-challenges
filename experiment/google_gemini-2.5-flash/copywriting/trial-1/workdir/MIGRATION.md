# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI v2 and provides step-by-step instructions and code examples to help experienced developers migrate their existing v1 integrations.

## What's New in v2

Zrb CLI v2 introduces significant enhancements, including native project support, improved pagination, and a more robust authentication mechanism. These changes bring greater flexibility and scalability but require updates to existing v1 client code.

---

## Breaking Changes

### 1. Endpoint Prefix Change

All API endpoints are now prefixed with `/v2/`. This ensures versioning and allows for future API evolution.

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

**Migration Example:**

```python
# v1: List tasks
response = requests.get("https://api.zrb.com/tasks", headers={"X-Auth-Token": MY_V1_API_KEY})

# v2: List tasks
response = requests.get("https://api.zrb.com/v2/tasks", headers={"Authorization": f"Bearer {MY_V2_API_TOKEN}"})
```

### 2. Authentication Header Changed

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is deprecated and replaced with a standard `Authorization: Bearer <token>` header.

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
# v1: Authentication header
headers = {
    "X-Auth-Token": MY_V1_API_KEY
}

# v2: Authentication header
headers = {
    "Authorization": f"Bearer {MY_V2_API_TOKEN}"
}
```

### 3. Task `id` Type Change

The `id` field for Task objects has transitioned from an integer to a UUID string. This provides a more robust and globally unique identifier for tasks.

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
  "completed": false
}
```

**Migration Example:**

```python
# v1: Fetch task by integer ID
task_id_v1 = 42
response = requests.get(f"https://api.zrb.com/tasks/{task_id_v1}", headers=V1_HEADERS)

# v2: Fetch task by UUID string ID
task_id_v2 = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
response = requests.get(f"https://api.zrb.com/v2/tasks/{task_id_v2}", headers=V2_HEADERS)
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed` for clearer semantics.

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

**Migration Example:**

```python
# v1: Update task with 'done' field
task_update_v1 = {
    "title": "Complete documentation",
    "done": True
}
requests.put(f"https://api.zrb.com/tasks/{task_id_v1}", json=task_update_v1, headers=V1_HEADERS)

# v2: Update task with 'completed' field
task_update_v2 = {
    "title": "Complete documentation",
    "completed": True
}
requests.put(f"https://api.zrb.com/v2/tasks/{task_id_v2}", json=task_update_v2, headers=V2_HEADERS)
```

### 5. Task Creation Requires `project_id`

Task creation (`POST /v2/tasks`) now mandates a `project_id` to associate tasks with a specific project. Omitting this field will result in an HTTP 422 Unprocessable Entity error.

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

**Migration Example:**

```python
# v1: Create task without project_id
new_task_v1 = {
    "title": "Refactor authentication module"
}
requests.post("https://api.zrb.com/tasks", json=new_task_v1, headers=V1_HEADERS)

# v2: Create task with project_id
new_task_v2 = {
    "title": "Refactor authentication module",
    "project_id": "project-frontend-xyz"
}
requests.post("https://api.zrb.com/v2/tasks", json=new_task_v2, headers=V2_HEADERS)
```

### 6. List Endpoints Return Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response encapsulated in an object, rather than a bare array of items. This object includes `items`, `total`, and `next_cursor` fields.

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
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Migration Example:**

```python
# v1: Iterate through all tasks (assuming small dataset)
response = requests.get("https://api.zrb.com/tasks", headers=V1_HEADERS)
for task in response.json():
    print(task["title"])

# v2: Iterate through paginated tasks
cursor = None
while True:
    params = {}
    if cursor:
        params["cursor"] = cursor
    
    response = requests.get("https://api.zrb.com/v2/tasks", params=params, headers=V2_HEADERS)
    data = response.json()
    
    for task in data["items"]:
        print(task["title"])
    
    cursor = data.get("next_cursor")
    if not cursor:
        break
```

---

## Migration Checklist

To successfully migrate your Zrb CLI v1 integration to v2, follow these steps:

1.  **Update API Endpoints**: Prefix all your Zrb API calls with `/v2/`.
2.  **Change Authentication**: Replace `X-Auth-Token` headers with `Authorization: Bearer <your_v2_api_token>`.
3.  **Refactor Task IDs**: Update any code that handles task IDs to expect and use UUID strings instead of integers.
4.  **Rename Completion Field**: Replace all occurrences of the `done` field with `completed` in task objects, especially in update operations.
5.  **Add `project_id` to Task Creation**: Ensure all `POST /v2/tasks` requests include a valid `project_id` in the request body.
6.  **Adjust List Endpoint Consumption**: Update code that consumes list endpoints (`GET /v2/tasks`) to expect and parse the new paginated envelope structure, iterating through the `items` array and handling `next_cursor` for pagination.
7.  **Thoroughly Test**: After making all changes, perform comprehensive testing of your integration to ensure all functionalities work as expected with the v2 API.

---

## Upgrade Command

To ensure you are using the latest Zrb CLI, run the following command:

```bash
zrb upgrade --version 2.0.0
```
