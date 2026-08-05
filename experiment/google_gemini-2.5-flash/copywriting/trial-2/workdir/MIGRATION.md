# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary steps to migrate your existing Zrb CLI v1 integrations to the new v2 API. Zrb v2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication. Please review all breaking changes carefully before upgrading.

## Breaking Changes

### 1. Endpoint Prefix Change

All API endpoints in v2 are now prefixed with `/v2/`. Requests to v1 endpoints without this prefix will fail.

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

**Code Example (using `curl`):**

**Before (v1):**
```bash
curl -X GET https://api.zrb.com/tasks \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**
```bash
curl -X GET https://api.zrb.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>"
```

### 2. Authentication Header Update

The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`. Requests using the old header will result in an HTTP 401 Unauthorized error.

**Before (v1):**

```
X-Auth-Token: <your_api_key>
```

**After (v2):**

```
Authorization: Bearer <your_api_token>
```

**Code Example (using `curl`):**

**Before (v1):**
```bash
curl -X POST https://api.zrb.com/tasks \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task", "project_id": "proj_abc123"}'
```

### 3. Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string. This affects all endpoints that reference a task by its ID (GET, PUT, DELETE).

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

**Code Example (fetching a task):**

**Before (v1):**
```bash
curl -X GET https://api.zrb.com/tasks/42 \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**
```bash
curl -X GET https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <your_api_token>"
```

### 4. Task Field `done` Renamed to `completed`

The boolean field `done` within the Task object has been renamed to `completed`. This impacts both how you read task status and how you update it.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Old task",
  "done": true
}
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-...",
  "title": "Old task",
  "completed": true,
  "project_id": "proj_abc123"
}
```

**Code Example (updating a task):**

**Before (v1):**
```bash
curl -X PUT https://api.zrb.com/tasks/42 \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

**After (v2):**
```bash
curl -X PUT https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

### 5. Task Creation Requires `project_id`

When creating new tasks, the `POST /v2/tasks` endpoint now requires a `project_id` field in the request body. Omitting it will result in an HTTP 422 Unprocessable Entity error.

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

**Code Example (creating a task):**

**Before (v1):**
```bash
curl -X POST https://api.zrb.com/tasks \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Plan v2 migration"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Plan v2 migration", "project_id": "dev_project"}'
```

### 6. List Endpoints Return Paginated Envelope

List endpoints (e.g., `GET /v2/tasks`) no longer return a bare array of items. Instead, they return a paginated envelope object containing the `items` array, `total` count, and `next_cursor` for pagination.

**Before (v1 Response):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 Response):**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Code Example (listing tasks):**

**Before (v1 - parsing response):**
```python
import requests

response = requests.get("https://api.zrb.com/tasks", headers={"X-Auth-Token": "<your_api_key>"})
tasks = response.json()
for task in tasks:
    print(f"Task: {task['title']}, Done: {task['done']}")
```

**After (v2 - parsing response and handling pagination):**
```python
import requests

headers = {"Authorization": "Bearer <your_api_token>"}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
data = response.json()
tasks = data['items']
next_cursor = data.get('next_cursor')

for task in tasks:
    print(f"Task: {task['title']}, Completed: {task['completed']}, Project: {task['project_id']}")

if next_cursor:
    print(f"Next page available with cursor: {next_cursor}")
    # Example: Fetching next page
    # response = requests.get(f"https://api.zrb.com/v2/tasks?cursor={next_cursor}", headers=headers)
    # ...
```

## Migration Checklist

To successfully migrate your Zrb CLI integrations from v1 to v2, follow these steps:

1.  **Update Endpoint Paths**: Prefix all Zrb API endpoint URLs with `/v2/`.
2.  **Change Authentication Header**: Replace `X-Auth-Token: <your_api_key>` with `Authorization: Bearer <your_api_token>`.
3.  **Adjust Task ID Handling**: Update your code to expect and use UUID strings for task IDs instead of integers.
4.  **Rename `done` to `completed`**: Change all references to the `done` field in Task objects to `completed`.
5.  **Provide `project_id` for Task Creation**: Ensure that all new task creation requests include a valid `project_id` in the request body.
6.  **Update List Endpoint Parsing**: Modify your code to parse the new paginated envelope response for list endpoints. Access task items via the `items` key in the response.
7.  **Implement Pagination (Optional but Recommended)**: Integrate logic to handle `next_cursor` for paginating through large result sets.
8.  **Test Thoroughly**: After making the changes, thoroughly test all API interactions with the v2 endpoints.

## Upgrade Command

To upgrade your Zrb CLI to the latest v2 version, run the following command:

```bash
zrb upgrade --version v2
```