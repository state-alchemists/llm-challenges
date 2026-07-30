# Zrb Task API v2 Migration Guide

This guide describes how to upgrade your integration from Zrb Task API v1 (detailed in `v1_spec.md`) to Zrb Task API v2 (detailed in `v2_spec.md`). 

v2 introduces support for projects, robust cursor-based pagination, and OAuth2-compliant bearer tokens, along with several breaking changes.

---

## Summary of Breaking Changes

The migration from v1 to v2 involves six major areas:
1. **Endpoint Versioning**: All paths are now prefixed with `/v2/` (`v2_spec.md:9`).
2. **Authentication Header**: Changed from `X-Auth-Token` to `Authorization: Bearer` (`v2_spec.md:10`).
3. **ID Format**: Changed from auto-incrementing integers to UUID strings (`v2_spec.md:11`).
4. **Field Renaming**: The `done` boolean field is renamed to `completed` (`v2_spec.md:12`).
5. **Required Fields**: Task creation now requires a `project_id` string (`v2_spec.md:13`).
6. **List Response Format**: List endpoints return a paginated object wrapper instead of a bare array (`v2_spec.md:14`).

---

## Detailed Breaking Changes and Code Examples

### 1. Endpoint Prefixing

All endpoints have been moved under the `/v2/` API namespace to allow versioning. Interacting with the old endpoints will yield an HTTP `404 Not Found`.

* **Before (v1)** (`v1_spec.md:32-82`): `/tasks`, `/tasks/{id}`
* **After (v2)** (`v2_spec.md:59-114`): `/v2/tasks`, `/v2/tasks/{id}`

#### Example (curl)

**Before (v1):**
```bash
curl -X GET https://api.zrb.dev/tasks
```

**After (v2):**
```bash
curl -X GET https://api.zrb.dev/v2/tasks
```

---

### 2. Authentication Header

The legacy custom header `X-Auth-Token` is replaced with standard OAuth2 Bearer token authorization. Requests using `X-Auth-Token` will return HTTP `401 Unauthorized`.

* **Before (v1)** (`v1_spec.md:5-11`): `X-Auth-Token: <your_api_key>`
* **After (v2)** (`v2_spec.md:18-26`): `Authorization: Bearer <your_api_token>`

#### Example (JavaScript/Fetch)

**Before (v1):**
```javascript
const response = await fetch('https://api.zrb.dev/tasks', {
  headers: {
    'X-Auth-Token': 'my_v1_api_key_12345'
  }
});
```

**After (v2):**
```javascript
const response = await fetch('https://api.zrb.dev/v2/tasks', {
  headers: {
    'Authorization': 'Bearer my_v2_api_token_54321'
  }
});
```

---

### 3. Task ID Format

Task identifier formats have transitioned from sequential integers to globally unique UUID strings (RFC 4122). Code structures expecting integers for validation, storage, or routing must be upgraded.

* **Before (v1)** (`v1_spec.md:15-28`): `id` is an integer (e.g. `42`).
* **After (v2)** (`v2_spec.md:30-43`): `id` is a 36-character UUID string (e.g. `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`).

#### Example (Python Validation)

**Before (v1):**
```python
# Expecting integer type matching v1 specification
def validate_task_id(task_id):
    if not isinstance(task_id, int):
        raise TypeError("Task ID must be an integer")
```

**After (v2):**
```python
import uuid

# Expecting UUID string format matching v2 specification
def validate_task_id(task_id):
    try:
        uuid.UUID(str(task_id))
    except ValueError:
        raise ValueError("Task ID must be a valid UUID string")
```

---

### 4. Task Field Renamed (`done` to `completed`)

To follow standard field naming guidelines, the boolean field `done` is now renamed to `completed`. This affects request bodies (`PUT /v2/tasks/{id}`) and response models.

* **Before (v1)** (`v1_spec.md:17`, `v1_spec.md:71`): `done` (boolean)
* **After (v2)** (`v2_spec.md:38`, `v2_spec.md:95`): `completed` (boolean)

#### Example (JSON Payloads)

**Before (v1):**
```json
{
  "title": "Upgrade SDK",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Upgrade SDK",
  "completed": true
}
```

#### Example (JavaScript UI Binding)

**Before (v1):**
```javascript
function renderTask(task) {
  const status = task.done ? 'Finished' : 'Pending';
  console.log(`Task: ${task.title} [${status}]`);
}
```

**After (v2):**
```javascript
function renderTask(task) {
  const status = task.completed ? 'Finished' : 'Pending';
  console.log(`Task: ${task.title} [${status}]`);
}
```

---

### 5. Task Creation Requires `project_id`

All tasks must belong to a project. A `project_id` string is now a required property on the task model. Sending a `POST /v2/tasks` request without `project_id` will return HTTP `422 Unprocessable Entity`.

* **Before (v1)** (`v1_spec.md:52-64`): Only `title` is required.
* **After (v2)** (`v2_spec.md:75-87`): Both `title` and `project_id` are required.

#### Example (Python/Requests)

**Before (v1):**
```python
import requests

payload = {
    "title": "Document v1 deprecation"
}
response = requests.post("https://api.zrb.dev/tasks", json=payload)
```

**After (v2):**
```python
import requests

payload = {
    "title": "Document v1 deprecation",
    "project_id": "proj_abc123"  # Mandatory v2 parameter
}
response = requests.post("https://api.zrb.dev/v2/tasks", json=payload)
```

---

### 6. List Response Pagination Envelope

List operations no longer return a bare JSON array. To support cursor-based pagination, list endpoints return an envelope containing `items`, `total`, and a `next_cursor` string.

* **Before (v1)** (`v1_spec.md:32-44`): Returns `[...]` (bare array).
* **After (v2)** (`v2_spec.md:45-55`): Returns `{"items": [...], "total": 42, "next_cursor": "cursor_xyz"}`.

#### Example (Node.js/Fetch - Iterative Fetching)

**Before (v1):**
```javascript
async function fetchAllTasks() {
  const response = await fetch('https://api.zrb.dev/tasks');
  const tasks = await response.json(); // Direct bare array
  return tasks;
}
```

**After (v2):**
```javascript
async function fetchAllTasks(apiToken) {
  let cursor = null;
  const allTasks = [];

  do {
    const url = 'https://api.zrb.dev/v2/tasks' + (cursor ? `?cursor=${cursor}` : '');
    const response = await fetch(url, {
      headers: { 'Authorization': `Bearer ${apiToken}` }
    });
    const data = await response.json(); // Paginated envelope
    allTasks.push(...data.items);
    cursor = data.next_cursor;
  } while (cursor);

  return allTasks;
}
```

---

## Step-by-Step Migration Checklist

Follow these steps to safely migrate your integration from v1 to v2:

- [ ] **Step 1: Upgrade CLI/SDK**  
  Upgrade the Zrb CLI environment using the installation/upgrade command.
  
- [ ] **Step 2: Update Base URL Prefix**  
  Update all integration base URLs to prepend `/v2` before the resource paths (e.g., change `/tasks` to `/v2/tasks`).

- [ ] **Step 3: Update Header Authentication**  
  Locate all instances of `X-Auth-Token` and convert them to standard OAuth2 Bearer authorization (`Authorization: Bearer <your_api_token>`).

- [ ] **Step 4: Audit Task ID Parsing & Storage**  
  Identify places expecting integer Task IDs (such as database schemas, validation functions, and URL parsers) and update them to support 36-character UUID string formats.

- [ ] **Step 5: Rename fields (`done` to `completed`)**  
  Search your codebase for references to task `.done` property and update them to `.completed`. Update writing payloads (`PUT`) and response parsers.

- [ ] **Step 6: Integrate `project_id` in Creation Flow**  
  Review your task creation logic (`POST /v2/tasks`) and ensure a valid `project_id` string is sent with every request payload.

- [ ] **Step 7: Implement Cursor Pagination**  
  Update list endpoint parsers (`GET /v2/tasks`) to extract the list array from the `.items` field of the returned JSON envelope, and add cursor pagination support using the `.next_cursor` parameter.

- [ ] **Step 8: Validate & Verify Integration**  
  Verify the changes against local or sandbox mock API endpoints before executing them in production environments.

---

## CLI Upgrade Command

To update your local Zrb CLI tool to version 2, execute:

```bash
pip install --upgrade zrb
```
