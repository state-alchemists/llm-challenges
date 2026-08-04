# Zrb CLI v1 to v2 Migration Guide

This guide provides a comprehensive overview of the breaking changes introduced in Zrb CLI v2 and offers clear steps to migrate your existing applications from v1. The new version brings significant improvements, including project support, enhanced pagination, and stricter authentication.

## Breaking Changes

### 1. Endpoint URL Prefix

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

**Example:** Fetching all tasks

```
# v1
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.com/tasks
```

```
# v2
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.com/v2/tasks
```

### 2. Authentication Header Change

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported. All requests must now use a Bearer token in the `Authorization` header.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Example:** Making an authenticated request

```python
# v1 Python example using requests
import requests
headers = {"X-Auth-Token": "YOUR_V1_API_KEY"}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
```

```python
# v2 Python example using requests
import requests
headers = {"Authorization": "Bearer YOUR_V2_API_TOKEN"}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
```

### 3. Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string. This affects all endpoints that reference tasks by their ID, as well as the structure of the Task object itself.

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

**Example:** Getting a specific task

```
# v1
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.com/tasks/42
```

```
# v2
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed` in the Task object. This affects `GET`, `POST`, and `PUT` operations involving task status.

**Before (v1):**
```json
{
  "title": "Finish report",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Finish report",
  "completed": true
}
```

**Example:** Updating a task's status

```
# v1
curl -X PUT -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"done": true}' \
  https://api.zrb.com/tasks/42
```

```
# v2
curl -X PUT -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}' \
  https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 5. Task Creation Requires `project_id`

When creating new tasks, the `project_id` field is now mandatory. Tasks must belong to a project.

**Before (v1):**
```json
{
  "title": "New important task"
}
```

**After (v2):**
```json
{
  "title": "New important task",
  "project_id": "proj_abc123"
}
```

**Example:** Creating a new task

```
# v1
curl -X POST -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Schedule team meeting"}' \
  https://api.zrb.com/tasks
```

```
# v2
curl -X POST -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Schedule team meeting", "project_id": "proj_abc123"}' \
  https://api.zrb.com/v2/tasks
```

### 6. List Endpoints Return a Paginated Envelope

List endpoints (e.g., `GET /v2/tasks`) no longer return a bare array of items. Instead, they return a paginated envelope containing the items, total count, and a `next_cursor` for pagination.

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
    {"id": "a1b2c3d4-e5f6...", "title": "Buy milk", "completed": false, "project_id": "proj_xyz", "created_at": "..."},
    {"id": "b2c3d4e5-f6a7...", "title": "Ship v2", "completed": true, "project_id": "proj_xyz", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Example:** Listing tasks and handling pagination

```python
# v1 Python example
import requests
headers = {"X-Auth-Token": "YOUR_V1_API_KEY"}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
tasks = response.json()
for task in tasks:
    print(task["title"])
```

```python
# v2 Python example
import requests
headers = {"Authorization": "Bearer YOUR_V2_API_TOKEN"}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
data = response.json()
tasks = data["items"]
for task in tasks:
    print(task["title"])
next_page_cursor = data.get("next_cursor")
if next_page_cursor:
    print(f"Next page available with cursor: {next_page_cursor}")
    # Fetch next page: requests.get(f"https://api.zrb.com/v2/tasks?cursor={next_page_cursor}", headers=headers)
```

## Migration Checklist

To migrate your Zrb CLI v1 integration to v2, follow these steps:

1.  **Update Zrb CLI:** Ensure you have the latest Zrb CLI installed. (e.g., `npm update -g zrb-cli` or `pip install --upgrade zrb-cli`, check Zrb documentation for specific command).
2.  **Adjust Endpoints:** Change all `/tasks` endpoint paths to `/v2/tasks`.
3.  **Update Authentication:**
    *   Replace `X-Auth-Token` headers with `Authorization: Bearer <your_v2_api_token>`.
    *   Obtain a new v2 API token if required.
4.  **Refactor Task IDs:** Update any code that handles task IDs to expect and work with UUID strings instead of integers. This includes parsing responses and constructing request URLs.
5.  **Rename Task `done` field:** Change all references to the `done` field in Task objects to `completed`. This applies to both reading task data and sending update requests.
6.  **Add `project_id` to Task Creation:** For any new task creation logic, ensure a valid `project_id` is included in the request body.
7.  **Adapt List Endpoint Responses:** Update code that processes responses from list endpoints to extract the actual task items from the `items` field within the new paginated envelope structure. Implement pagination logic using the `next_cursor` if you need to fetch all results.
8.  **Test thoroughly:** After making the changes, rigorously test your application against the new Zrb CLI v2 API to ensure full compatibility.

## Upgrade Command

To ensure you have the latest Zrb CLI, please refer to the official Zrb documentation for the most up-to-date upgrade instructions. A common method might be:

```bash
# Example: For Node.js-based CLI
npm update -g zrb-cli

# Example: For Python-based CLI
pip install --upgrade zrb-cli
```
Please replace with the actual command for your specific Zrb CLI installation.
