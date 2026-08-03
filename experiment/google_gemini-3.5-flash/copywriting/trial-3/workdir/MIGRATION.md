# Zrb Task API — v1 to v2 Migration Guide

This guide describes the breaking changes introduced in Zrb CLI/API v2 and provides instructions on how to migrate your existing v1 integrations to v2.

## Table of Contents
- [Overview](#overview)
- [Breaking Changes](#breaking-changes)
  1. [Endpoint Prefixing (`/v2/`)](#1-endpoint-prefixing-v2)
  2. [Authentication Header Change](#2-authentication-header-change)
  3. [Task ID Type Change (Integer to UUID)](#3-task-id-type-change-integer-to-uuid)
  4. [Task Field Renamed (`done` to `completed`)](#4-task-field-renamed-done-to-completed)
  5. [Task Creation Requires `project_id`](#5-task-creation-requires-project_id)
  6. [List Endpoints Return Paginated Envelope](#6-list-endpoints-return-paginated-envelope)
- [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
- [Upgrade Command](#upgrade-command)

---

## Overview

Zrb v2 introduces projects, improved pagination, and stricter, standard authentication. While these changes make the API more robust, they introduce several breaking changes for developers migrating from v1.

All requests to the old v1 endpoints or utilizing v1-style schemas and headers will fail (returning HTTP `401 Unauthorized`, `404 Not Found`, or `422 Unprocessable Entity`).

---

## Breaking Changes

### 1. Endpoint Prefixing (`/v2/`)

All API routes in v2 are now prefixed with `/v2/`. Legacy v1 paths (such as `/tasks`) are no longer supported.

#### Before (v1)
Legacy endpoints did not have a version prefix:
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

And in standard integration code (e.g., Python `requests`):

**Before (v1)**
```python
import requests

BASE_URL = "https://api.zrb.dev"
response = requests.get(f"{BASE_URL}/tasks")
```

**After (v2)**
```python
import requests

BASE_URL = "https://api.zrb.dev"
response = requests.get(f"{BASE_URL}/v2/tasks")
```

---

### 2. Authentication Header Change

The custom authentication header `X-Auth-Token` has been replaced with the standard OAuth2/OIDC Bearer token schema via the `Authorization` header. Sending `X-Auth-Token` in v2 requests will result in an HTTP `401 Unauthorized` response.

#### Before (v1)
Authentication utilized the custom `X-Auth-Token` header:
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key_here
```

#### After (v2)
Authentication requires the standard `Authorization` header with a `Bearer` token prefix:
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token_here
```

And in integration code (e.g., JavaScript/Node.js `fetch`):

**Before (v1)**
```javascript
const response = await fetch("https://api.zrb.dev/tasks", {
  headers: {
    "X-Auth-Token": "your_api_key_here"
  }
});
```

**After (v2)**
```javascript
const response = await fetch("https://api.zrb.dev/v2/tasks", {
  headers: {
    "Authorization": "Bearer your_api_token_here"
  }
});
```

---

### 3. Task ID Type Change (Integer to UUID)

In v1, the Task `id` field was an auto-assigned integer. In v2, Task `id`s are standard UUID strings. If your database schemas, local client types, parsing logic, or route params assume integer IDs, they must be updated to handle strings.

#### Before (v1)
Task objects returned integer IDs:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2)
Task objects return UUID strings for the `id` field:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

In your application code or type definitions:

**Before (v1)**
```typescript
interface Task {
  id: number;
  title: string;
  done: boolean;
  created_at: string;
}

// Client requests with integer ID
const taskId = 42;
const response = await fetch(`https://api.zrb.dev/tasks/${taskId}`);
```

**After (v2)**
```typescript
interface Task {
  id: string; // Updated to string/UUID
  title: string;
  completed: boolean;
  project_id: string;
  created_at: string;
}

// Client requests with UUID string ID
const taskId = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
const response = await fetch(`https://api.zrb.dev/v2/tasks/${taskId}`);
```

---

### 4. Task Field Renamed (`done` to `completed`)

The boolean field representing the task completion status has been renamed from `done` to `completed` for consistency and clarity.

#### Before (v1)
The task completion field was `done`:
```json
{
  "id": 1,
  "title": "Buy milk",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2)
The task completion field is `completed`:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Buy milk",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

In update request payloads and client parsing:

**Before (v1)**
```python
# Create update request
payload = {"done": True}
response = requests.put("https://api.zrb.dev/tasks/123", json=payload)

# Parsing status
is_done = response.json()["done"]
```

**After (v2)**
```python
# Create update request
payload = {"completed": True}
response = requests.put("https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890", json=payload)

# Parsing status
is_completed = response.json()["completed"]
```

---

### 5. Task Creation Requires `project_id`

Zrb v2 introduces a scoped task-organization model. Task creation (`POST /v2/tasks`) now requires an associated `project_id`. Sending a task creation payload without `project_id` will trigger an HTTP `422 Unprocessable Entity` validation error.

#### Before (v1)
Only the task `title` was required:
```json
{
  "title": "New task title"
}
```

#### After (v2)
Both `title` and `project_id` are required:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

In integration code:

**Before (v1)**
```python
payload = {
    "title": "Automate all things"
}
response = requests.post("https://api.zrb.dev/tasks", json=payload)
```

**After (v2)**
```python
payload = {
    "title": "Automate all things",
    "project_id": "proj_abc123"  # Required field
}
response = requests.post("https://api.zrb.dev/v2/tasks", json=payload)
```

---

### 6. List Endpoints Return Paginated Envelope

To avoid loading excessive datasets and to support robust pagination, the `/v2/tasks` endpoint returns a paginated JSON envelope containing pagination metadata and an array of items, instead of the legacy bare JSON array.

#### Before (v1)
Legacy list endpoints returned a bare JSON array of tasks:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "2024-01-15T10:30:00Z"},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "2024-01-15T10:30:00Z"}
]
```

#### After (v2)
v2 list endpoints return a paginated JSON object:
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

In client response processing:

**Before (v1)**
```python
# Processing bare array directly
tasks = response.json()
for task in tasks:
    print(f"Task: {task['title']}, Done: {task['done']}")
```

**After (v2)**
```python
# Processing paginated envelope
envelope = response.json()
tasks = envelope["items"]
total_items = envelope["total"]
next_page_cursor = envelope["next_cursor"]

for task in tasks:
    print(f"Task: {task['title']}, Completed: {task['completed']}")
```

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your existing codebase to the v2 Zrb CLI and API:

- [ ] **Upgrade the Zrb CLI** using the package manager command below.
- [ ] **Update your Endpoint Base Paths** by adding the `/v2/` prefix to your API endpoints in configuration files and utility methods.
- [ ] **Modify Authentication Header Keys** from `X-Auth-Token` to `Authorization: Bearer <your_api_token>` in all API requests.
- [ ] **Refactor Task ID Data Types** from integer (`int` / `number`) to string/UUID in database schemas, type files (TypeScript, Go, etc.), and local models.
- [ ] **Rename Status Fields** from `done` to `completed` across JSON serializer configs, model attributes, state hooks, and conditional logic.
- [ ] **Inject `project_id` into Task Creations**: Update your task-creation functions and forms to require and supply a valid `project_id`.
- [ ] **Update List Parsing**: Adapt your response-handling code for list endpoints (`/v2/tasks`) to extract data from the `items` property of the returned JSON envelope, and add cursor-based pagination handling if necessary.
- [ ] **Run Integration Tests**: Execute your local, staging, or CI test suite against the v2 environment to ensure compatibility and that no HTTP `401`, `422`, or `404` errors are returned.

---

## Upgrade Command

To upgrade the Zrb CLI to version 2, execute the following command:

```bash
pip install --upgrade zrb
```
