# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI v2 and provides instructions and code examples to help experienced v1 users migrate their applications.

## Summary of Breaking Changes

Zrb CLI v2 introduces several significant changes to improve the API's consistency, scalability, and feature set. The key breaking changes are:

1.  **API Endpoint Prefix**: All API endpoints are now prefixed with `/v2/`.
2.  **Authentication Header**: The authentication mechanism has shifted from a custom header to a standard Bearer token.
3.  **Task ID Type**: Task identifiers (`id`) are now UUID strings instead of integers.
4.  **Task Field Renamed**: The `done` field on Task objects has been renamed to `completed`.
5.  **Project Requirement for Task Creation**: Creating new tasks now requires a `project_id`.
6.  **Paginated List Responses**: List endpoints now return a paginated envelope rather than a bare array of items.

---

## Detailed Breaking Changes and Migration Steps

### 1. API Endpoint Prefix Change

All API endpoints in v2 are now prefixed with `/v2/`. This requires updating all your API call paths.

**Before (v1):**
```http
GET /tasks
POST /tasks
GET /tasks/{id}
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
```

**Migration Example (Conceptual):**

```python
# Before (v1)
# response = requests.get("https://api.zrb.com/tasks")

# After (v2)
# response = requests.get("https://api.zrb.com/v2/tasks")
```

### 2. Authentication Header Changed

The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`. Requests using the old header will receive an HTTP 401 Unauthorized response.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

**Migration Example (Conceptual):**

```python
# Before (v1)
# headers = {"X-Auth-Token": "your_api_key_v1"}
# response = requests.get("https://api.zrb.com/tasks", headers=headers)

# After (v2)
# headers = {"Authorization": "Bearer your_api_token_v2"}
# response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
```

### 3. Task ID Type Changed

The `id` field for Task objects is no longer an integer; it is now a UUID string. This affects how you store, retrieve, update, and delete tasks.

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
  "completed": false,
  "project_id": "proj_abc123"
}
```

**Migration Example (Conceptual - Get Task):**

```python
# Before (v1)
# task_id = 42
# response = requests.get(f"https://api.zrb.com/tasks/{task_id}")

# After (v2)
# task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
# response = requests.get(f"https://api.zrb.com/v2/tasks/{task_id}")
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. This impacts task object deserialization and any update requests.

**Before (v1 - Update Task Request Body):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 - Update Task Request Body):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

**Migration Example (Conceptual - Update Task):**

```python
# Before (v1)
# task_data = {"done": True}
# response = requests.put(f"https://api.zrb.com/tasks/{task_id}", json=task_data)
# is_done = response.json()["done"]

# After (v2)
# task_data = {"completed": True}
# response = requests.put(f"https://api.zrb.com/v2/tasks/{task_id}", json=task_data)
# is_completed = response.json()["completed"]
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, you must now include a `project_id` in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity response.

**Before (v1 - Create Task Request Body):**
```json
{
  "title": "New task title"
}
```

**After (v2 - Create Task Request Body):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Migration Example (Conceptual - Create Task):**

```python
# Before (v1)
# task_data = {"title": "Build new feature"}
# response = requests.post("https://api.zrb.com/tasks", json=task_data)

# After (v2)
# task_data = {"title": "Build new feature", "project_id": "proj_456"}
# response = requests.post("https://api.zrb.com/v2/tasks", json=task_data)
```

### 6. List Endpoints Return a Paginated Envelope

The `List Tasks` endpoint (and other list endpoints, if any) no longer returns a bare array of task objects. Instead, it returns a paginated envelope containing `items`, `total`, and `next_cursor` fields.

**Before (v1 - List Tasks Response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "..."},
  {"id": 2, "title": "Ship v1", "done": true, "..."},
  ...
]
```

**After (v2 - List Tasks Response):**
```json
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "...", "..."},
    {"id": "b3c4...", "title": "Ship v1", "completed": true, "project_id": "...", "..."},
    ...
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Migration Example (Conceptual - List Tasks):**

```python
# Before (v1)
# response = requests.get("https://api.zrb.com/tasks")
# tasks = response.json()
# for task in tasks:
#     print(task["title"])

# After (v2)
# response = requests.get("https://api.zrb.com/v2/tasks")
# paginated_response = response.json()
# tasks = paginated_response["items"]
# for task in tasks:
#     print(task["title"])
# next_cursor = paginated_response.get("next_cursor")
# if next_cursor:
#     # Handle pagination: make another request with ?cursor=next_cursor
#     pass
```

---

## Migration Checklist

To successfully upgrade your application to Zrb CLI v2, follow these steps:

1.  [ ] **Update API Base Paths**: Change all `/tasks` endpoints to `/v2/tasks`.
2.  [ ] **Modify Authentication**: Replace `X-Auth-Token` headers with `Authorization: Bearer <your_api_token>`.
3.  [ ] **Adjust Task ID Handling**: Update your code to expect and handle UUID strings for task `id`s instead of integers. This includes storage, retrieval, and all API calls that take an `id` as a path parameter.
4.  [ ] **Rename Task Completion Field**: Change all references to the `done` field to `completed` in both your code and API request/response handling.
5.  [ ] **Add `project_id` to Task Creation**: Ensure all `POST /v2/tasks` requests include a valid `project_id` in the request body.
6.  [ ] **Adapt List Endpoint Parsing**: Update your code to parse the new paginated response envelope for list endpoints, accessing items via `response.json()["items"]`. Implement pagination logic using `next_cursor` if needed.
7.  [ ] **Test Thoroughly**: After making the above changes, thoroughly test your application's interaction with the Zrb CLI v2 API.

---

## Upgrade Command

To update your Zrb CLI installation to v2, run the following command:

```bash
zrb upgrade --version 2
```
