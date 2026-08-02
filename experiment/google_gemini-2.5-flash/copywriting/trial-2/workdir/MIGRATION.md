# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary changes to migrate your applications from Zrb CLI v1 to v2. Version 2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication, which involve several breaking changes.

The audience for this guide is experienced developers already familiar with Zrb CLI v1.

## Breaking Changes

### 1. Endpoint Prefix Change

All API endpoints are now prefixed with `/v2/`. Requests to v1 endpoints without this prefix will no longer work.

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

**Before Code Example (v1 Python):**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}

response = requests.get("https://api.zrb.com/tasks", headers=headers)
tasks = response.json()
print(tasks)
```

**After Code Example (v2 Python):**
```python
import requests

# Note: Authentication header also changed, see next section
api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}

response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
# Note: Response structure also changed, see pagination section
paginated_response = response.json()
print(paginated_response)
```

### 2. Authentication Header Changed

The authentication mechanism has been updated from a custom `X-Auth-Token` header to a standard `Authorization: Bearer` token.

**Before (v1 header):**
```
X-Auth-Token: <your_api_key>
```

**After (v2 header):**
```
Authorization: Bearer <your_api_token>
```

**Before Code Example (v1 Node.js):**
```javascript
const axios = require('axios');

const apiKey = 'your_v1_api_key';
axios.defaults.headers.common['X-Auth-Token'] = apiKey;

axios.get('https://api.zrb.com/tasks')
  .then(response => console.log(response.data))
  .catch(error => console.error(error));
```

**After Code Example (v2 Node.js):**
```javascript
const axios = require('axios');

const apiToken = 'your_v2_api_token';
axios.defaults.headers.common['Authorization'] = `Bearer ${apiToken}`;

axios.get('https://api.zrb.com/v2/tasks') // Note: Endpoint also changed
  .then(response => console.log(response.data))
  .catch(error => console.error(error));
```

### 3. Task `id` Type Changed to UUID String

Task identifiers (`id`) are no longer integers but universally unique identifiers (UUIDs) represented as strings. This affects fetching, updating, and deleting tasks.

**Before (v1 `id`):** `42`
**After (v2 `id`):** `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`

**Before Code Example (v1 Fetch Task):**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
task_id = 42

response = requests.get(f"https://api.zrb.com/tasks/{task_id}", headers=headers)
task = response.json()
print(task)
```

**After Code Example (v2 Fetch Task):**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890" # Must be a UUID string

response = requests.get(f"https://api.zrb.com/v2/tasks/{task_id}", headers=headers) # Note: Endpoint also changed
task = response.json()
print(task)
```

### 4. Task Field `done` Renamed to `completed`

The boolean field `done` in the Task Object has been renamed to `completed`. This affects task creation and updates where you explicitly set the status.

**Before (v1 Task Object):**
```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "..." }
```

**After (v2 Task Object):**
```json
{ "id": "...", "title": "Write tests", "completed": false, "project_id": "...", "created_at": "..." }
```

**Before Code Example (v1 Update Task):**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
task_id = 42
payload = {"done": True}

response = requests.put(f"https://api.zrb.com/tasks/{task_id}", headers=headers, json=payload)
updated_task = response.json()
print(updated_task)
```

**After Code Example (v2 Update Task):**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
payload = {"completed": True} # Renamed from 'done'

response = requests.put(f"https://api.zrb.com/v2/tasks/{task_id}", headers=headers, json=payload) # Note: Endpoint also changed
updated_task = response.json()
print(updated_task)
```

### 5. Task Creation Now Requires `project_id`

When creating a new task, you must now include a `project_id` in the request body. Omitting this will result in an HTTP 422 error.

**Before (v1 Create Task Request):**
```json
{
  "title": "New task title"
}
```

**After (v2 Create Task Request):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Before Code Example (v1 Create Task):**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
payload = {"title": "Develop new feature"}

response = requests.post("https://api.zrb.com/tasks", headers=headers, json=payload)
created_task = response.json()
print(created_task)
```

**After Code Example (v2 Create Task):**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
payload = {
  "title": "Develop new feature",
  "project_id": "proj_abc123" # New required field
}

response = requests.post("https://api.zrb.com/v2/tasks", headers=headers, json=payload) # Note: Endpoint also changed
created_task = response.json()
print(created_task)
```

### 6. List Endpoints Return Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response wrapped in an envelope object, rather than a bare array of items.

**Before (v1 List Tasks Response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 List Tasks Response):**
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

To fetch the next page, you will pass the `next_cursor` as a query parameter: `?cursor=<next_cursor>`. The `limit` query parameter can also be used to control the number of results per page (default 20).

**Before Code Example (v1 Process List Response):**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}

response = requests.get("https://api.zrb.com/tasks", headers=headers)
tasks = response.json() # Direct array
for task in tasks:
    print(f"Task ID: {task['id']}, Title: {task['title']}, Done: {task['done']}")
```

**After Code Example (v2 Process List Response):**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}

response = requests.get("https://api.zrb.com/v2/tasks", headers=headers) # Note: Endpoint also changed
paginated_response = response.json() # Envelope object
tasks = paginated_response["items"] # Access items from the 'items' key
for task in tasks:
    # Note: 'done' is now 'completed'
    print(f"Task ID: {task['id']}, Title: {task['title']}, Completed: {task['completed']}")

# Example of fetching next page
next_cursor = paginated_response.get("next_cursor")
if next_cursor:
    print(f"Fetching next page with cursor: {next_cursor}")
    next_page_response = requests.get(f"https://api.zrb.com/v2/tasks?cursor={next_cursor}", headers=headers)
    next_page_data = next_page_response.json()
    print(next_page_data["items"])
```

## Migration Checklist

To successfully migrate your Zrb CLI v1 applications to v2, follow these steps:

1.  [ ] **Update CLI to v2**: Ensure your Zrb CLI is updated to the latest v2 version.
2.  [ ] **Review Authentication**: Replace all instances of `X-Auth-Token` in your headers with `Authorization: Bearer <your_api_token>`.
3.  [ ] **Adjust Endpoint Paths**: Prefix all Zrb API endpoint calls with `/v2/`.
4.  [ ] **Handle `id` Type Change**: Update any code that handles task IDs to expect and use UUID strings instead of integers. This includes URL parameters and data parsing.
5.  [ ] **Rename `done` to `completed`**: Globally replace references to the `done` field with `completed` in your task objects, especially in creation and update payloads.
6.  [ ] **Add `project_id` to Task Creation**: Modify all task creation requests (`POST /v2/tasks`) to include a `project_id` in the request body.
7.  [ ] **Update List Response Parsing**: Modify code that consumes list endpoints (e.g., `GET /v2/tasks`) to expect a paginated envelope. Access task items from the `items` key of the response and implement pagination logic using `next_cursor` if needed.
8.  [ ] **Test Thoroughly**: After making all code changes, rigorously test your application against the new Zrb CLI v2 API to ensure all functionalities work as expected.

## Upgrade Command

To upgrade your Zrb CLI to the latest v2 version, run:

```bash
zrb upgrade --to v2
```
