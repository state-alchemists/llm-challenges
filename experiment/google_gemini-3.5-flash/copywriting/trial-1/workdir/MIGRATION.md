# Zrb CLI v2 Migration Guide

This guide is designed to help you migrate your applications and integrations from Zrb CLI v1 to v2.

## Table of Contents
- [Overview](#overview)
- [Summary of Breaking Changes](#summary-of-breaking-changes)
- [Breaking Changes Details](#breaking-changes-details)
  1. [Base URL Path Prefix (`/v2/`)](#1-base-url-path-prefix-v2)
  2. [Authentication Header (`Authorization: Bearer`)](#2-authentication-header-authorization-bearer)
  3. [Task ID Data Type (Integer to UUID)](#3-task-id-data-type-integer-to-uuid)
  4. [Completion Status Field Name (`done` to `completed`)](#4-completion-status-field-name-done-to-completed)
  5. [Mandatory `project_id` on Task Creation](#5-mandatory-project_id-on-task-creation)
  6. [Paginated Envelope for List Endpoints](#6-paginated-envelope-for-list-endpoints)
- [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
- [Upgrade Command](#upgrade-command)

---

## Overview

Zrb v2 introduces first-class support for projects, improved cursor-based pagination, and stricter security protocols. While these improvements significantly enhance the robustness and scalability of the Zrb platform, they introduce breaking changes to the REST API and data models.

---

## Summary of Breaking Changes

| # | Breaking Change | Impact |
|---|---|---|
| 1 | Endpoint URLs prefixed with `/v2/` | All API request paths must be updated. |
| 2 | Authentication header changed to `Bearer` | `X-Auth-Token` is deprecated; requests using it return `401 Unauthorized`. |
| 3 | Task `id` is now a UUID string | Database schema and client-side parsers must accept UUIDs instead of integers. |
| 4 | Task field `done` renamed to `completed` | Serialization/deserialization and payload keys must use `completed`. |
| 5 | Task creation requires `project_id` | `POST /v2/tasks` payloads without a valid `project_id` return `422 Unprocessable Entity`. |
| 6 | List endpoints return a paginated envelope | Response parsers must read the `.items` array instead of a bare list. |

---

## Breaking Changes Details

### 1. Base URL Path Prefix (`/v2/`)
All endpoints have been moved under the `/v2/` namespace to support future versioning.

#### Before (v1)
Endpoints were hosted directly under the root domain:
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
```

#### After (v2)
All endpoints must be prefixed with `/v2/`:
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
```

---

### 2. Authentication Header (`Authorization: Bearer`)
The authentication mechanism has transitioned to a standard Bearer token scheme.

#### Before (v1)
API keys were passed via the custom `X-Auth-Token` header:
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: zrb_token_v1_xyz
```

#### After (v2)
Tokens must be passed using the standard HTTP `Authorization` header with the `Bearer` prefix. Using the old `X-Auth-Token` header will result in an `HTTP 401 Unauthorized` response:
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer zrb_token_v2_abc
```

---

### 3. Task ID Data Type (Integer to UUID)
Task identifiers have been upgraded from sequential integers to standard UUID strings to prevent ID enumeration and facilitate distributed task generation.

#### Before (v1)
The task ID was an integer:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```
Client URL path reference:
```http
GET /tasks/42 HTTP/1.1
```

#### After (v2)
The task ID is now a 36-character UUID string:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```
Client URL path reference:
```http
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
```

---

### 4. Completion Status Field Name (`done` to `completed`)
To align with standard API naming conventions, the task model's boolean field representing progress has been renamed.

#### Before (v1)
The progress status field was named `done`:
```json
{
  "title": "Updated title",
  "done": true
}
```

Updating a task in Python (v1):
```python
import requests

response = requests.put(
    "https://api.zrb.dev/tasks/42",
    headers={"X-Auth-Token": "my-token"},
    json={"done": True}
)
```

#### After (v2)
The progress status field is named `completed`:
```json
{
  "title": "Updated title",
  "completed": true
}
```

Updating a task in Python (v2):
```python
import requests

response = requests.put(
    "https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    headers={"Authorization": "Bearer my-token"},
    json={"completed": True}
)
```

---

### 5. Mandatory `project_id` on Task Creation
Tasks are now scoped inside a logical project. Creating a task without specifying a `project_id` is no longer supported.

#### Before (v1)
Tasks could be created with just a `title`:
```json
{
  "title": "New task title"
}
```

#### After (v2)
Task creation payloads **must** include a valid `project_id`. Omitting this field results in an `HTTP 422 Unprocessable Entity` error:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Envelope for List Endpoints
To optimize data transfer and support larger datasets, list endpoints now return a paginated JSON envelope rather than a raw, bare array.

#### Before (v1)
`GET /tasks` returned a bare JSON array:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

Parsing list in Python (v1):
```python
response = requests.get("https://api.zrb.dev/tasks", headers={"X-Auth-Token": "..."})
tasks = response.json()
print(f"Total tasks retrieved: {len(tasks)}")
for task in tasks:
    print(task["title"])
```

#### After (v2)
`GET /v2/tasks` returns an envelope object containing `items`, `total`, and a `next_cursor` string (or `null`/omitted when no more pages exist). Pagination is advanced by passing the cursor via query parameter `?cursor=<next_cursor>`.
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "..."
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Parsing list and paginating in Python (v2):
```python
import requests

url = "https://api.zrb.dev/v2/tasks"
headers = {"Authorization": "Bearer your_token"}
params = {"limit": 20}

while url:
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    
    # Process batch of items
    for task in data["items"]:
        print(task["title"])
        
    next_cursor = data.get("next_cursor")
    if next_cursor:
        # Update params with next cursor for subsequent iteration
        params["cursor"] = next_cursor
    else:
        break
```

---

## Step-by-Step Migration Checklist

Follow these steps to upgrade your code and infrastructure to Zrb v2:

- [ ] **Step 1: Locate all API call sites** — Search your codebase for calls to `/tasks` or dependencies referencing the Zrb v1 API.
- [ ] **Step 2: Update endpoint URL paths** — Prepend `/v2` to every Zrb API URL (e.g., replace `/tasks` with `/v2/tasks`).
- [ ] **Step 3: Update authentication headers** — Change headers from `X-Auth-Token: <api_key>` to `Authorization: Bearer <api_token>`.
- [ ] **Step 4: Update task creation payloads** — Ensure every task creation call (`POST`) includes the required `"project_id"` parameter.
- [ ] **Step 5: Refactor task update and parser fields** — Rename all references of `"done"` to `"completed"` in both payload requests and response parsing.
- [ ] **Step 6: Update ID handling** — Adjust database schemas, ORM attributes, and routing logic to accept a UUID `string` instead of an `integer`.
- [ ] **Step 7: Refactor list response parsing** — Modify response handlers for list endpoints to parse the `"items"` array inside the return object, instead of treating the root response as a list.
- [ ] **Step 8: Implement cursor-based pagination** — If you retrieve multiple pages of tasks, update your loop logic to handle `next_cursor` and pass it as a `?cursor=` query parameter.
- [ ] **Step 9: Run tests and verify integrations** — Execute your test suite and perform integration testing using the new v2 endpoints to verify the upgrade.

---

## Upgrade Command

To upgrade the Zrb CLI to the latest v2 release, run:

```bash
pip install --upgrade zrb
```
