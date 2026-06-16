# Zrb CLI v2 Migration Guide

This guide details the breaking changes and necessary steps to migrate your existing Zrb CLI v1 integrations to v2. Version 2 introduces significant enhancements, including project management, improved pagination, and stricter authentication.

## Key Changes in v2

Zrb CLI v2 focuses on improved scalability and project organization:
-   **Projects**: Tasks can now be organized under projects.
-   **Enhanced Pagination**: List endpoints now provide cursor-based pagination for more efficient data retrieval.
-   **Stricter Authentication**: A more standardized Bearer token authentication mechanism is introduced.

## Breaking Changes

The following changes require modifications to your existing v1 integrations.

### 1. Endpoint Prefix Change

All API endpoints are now prefixed with `/v2/`. Requests to v1 paths will no longer work.

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

**Example: Listing tasks**

**v1 Request:**
```bash
curl -H "X-Auth-Token: <your_api_key>" \
     http://api.zrb.com/tasks
```

**v2 Request:**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
     http://api.zrb.com/v2/tasks
```

### 2. Authentication Header Changed

The authentication mechanism has moved from a custom `X-Auth-Token` header to a standard `Authorization: Bearer` token. Requests using `X-Auth-Token` will receive an HTTP 401 Unauthorized response.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Example: Authenticated request**

**v1 Code:**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
response = requests.get("http://api.zrb.com/tasks", headers=headers)
print(response.json())
```

**v2 Code:**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
response = requests.get("http://api.zrb.com/v2/tasks", headers=headers)
print(response.json())
```

### 3. Task `id` Type Changed from Integer to UUID String

The `id` field for Task objects is now a UUID string instead of an integer. This affects all endpoints that reference tasks by ID (Get, Update, Delete).

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

**Example: Getting a specific task**

**v1 Request:**
```bash
curl -H "X-Auth-Token: <your_api_key>" \
     http://api.zrb.com/tasks/42
```

**v2 Request:**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
     http://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 4. Task Field `done` Renamed to `completed`

The boolean field `done` in the Task object has been renamed to `completed` for improved clarity.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Buy milk",
  "done": true
}
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Buy milk",
  "completed": true
}
```

**Example: Updating a task's status**

**v1 Request Body:**
```json
{
  "done": true
}
```

**v2 Request Body:**
```json
{
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, the `project_id` field is now a mandatory string. Omitting it will result in an HTTP 422 Unprocessable Entity error.

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

**Example: Creating a task**

**v1 Code:**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
data = {"title": "Refactor authentication module"}
response = requests.post("http://api.zrb.com/tasks", headers=headers, json=data)
print(response.json())
```

**v2 Code:**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
data = {
    "title": "Refactor authentication module",
    "project_id": "proj_dev_team" # Replace with your project ID
}
response = requests.post("http://api.zrb.com/v2/tasks", headers=headers, json=data)
print(response.json())
```

### 6. List Endpoints Return a Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated envelope object instead of a bare array of items. The response includes `items`, `total`, and `next_cursor` fields.

**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "..."},
  {"id": 2, "title": "Ship v1", "done": true, "..."},
  ...
]
```

**After (v2):**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "...", "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "...", "..."},
    ...
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, include the `cursor` query parameter from `next_cursor`. You can also control the number of results per page using the `limit` query parameter.

**Example: Iterating through tasks**

**v1 Code:**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
response = requests.get("http://api.zrb.com/tasks", headers=headers)
for task in response.json():
    print(task["title"])
```

**v2 Code:**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
base_url = "http://api.zrb.com/v2/tasks"
next_cursor = None

while True:
    params = {}
    if next_cursor:
        params["cursor"] = next_cursor

    response = requests.get(base_url, headers=headers, params=params)
    data = response.json()

    for task in data["items"]:
        print(task["title"])

    next_cursor = data.get("next_cursor")
    if not next_cursor:
        break
```

## Migration Checklist

Follow these steps to migrate your Zrb CLI v1 integrations to v2:

1.  **Update Authentication:**
    *   Change all `X-Auth-Token` headers to `Authorization: Bearer <your_api_token>`.
    *   Ensure you are using a v2 compatible API token.

2.  **Adjust Endpoint Paths:**
    *   Prefix all `/tasks` endpoints with `/v2/` (e.g., `/tasks` becomes `/v2/tasks`).

3.  **Refactor Task ID Handling:**
    *   Update your code to expect and handle UUID strings for task IDs instead of integers.

4.  **Rename `done` to `completed`:**
    *   Modify any references to the `done` field in Task objects to `completed`.

5.  **Add `project_id` to Task Creation:**
    *   Ensure all `POST /v2/tasks` requests include a valid `project_id` in the request body.

6.  **Update List Endpoint Parsing:**
    *   Modify your code to parse the paginated envelope response (`items`, `total`, `next_cursor`) from list endpoints.
    *   Implement logic to handle pagination using the `next_cursor` and `limit` parameters if necessary.

## Upgrade Command

To ensure your Zrb CLI is up to date, run the following command:

```bash
zrb upgrade
```

This will update your local Zrb CLI installation to the latest version, including v2 API support.
