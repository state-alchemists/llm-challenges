# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes and necessary steps to migrate your applications from Zrb CLI v1 to v2. Version 2 introduces significant improvements, including project support, improved pagination, and stricter authentication.

## Table of Contents

- [Introduction](#introduction)
- [Breaking Changes](#breaking-changes)
  - [1. Endpoint Prefix Change](#1-endpoint-prefix-change)
  - [2. Authentication Header Update](#2-authentication-header-update)
  - [3. Task ID Type Change (Integer to UUID)](#3-task-id-type-change-integer-to-uuid)
  - [4. Task Field Renamed: `done` to `completed`](#4-task-field-renamed-done-to-completed)
  - [5. Task Creation Requires `project_id`](#5-task-creation-requires-project_id)
  - [6. List Endpoints Return Paginated Envelope](#6-list-endpoints-return-paginated-envelope)
- [Migration Checklist](#migration-checklist)
- [Upgrade Command](#upgrade-command)

---

## Introduction

Zrb CLI v2 brings new features and stability improvements, but it also includes several breaking changes that require updates to your existing v1 integrations. This guide will help you navigate these changes.

## Breaking Changes

### 1. Endpoint Prefix Change

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

**Example (HTTP request):**

**v1:**
```http
GET /tasks HTTP/1.1
Host: api.zrb.com
X-Auth-Token: <your_api_key>
```

**v2:**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.com
Authorization: Bearer <your_api_token>
```

### 2. Authentication Header Update

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported. All requests must now use a Bearer token in the `Authorization` header.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Example (Python using `requests`):**

**v1:**
```python
import requests

api_key = "your_v1_api_key"
headers = {"X-Auth-Token": api_key}
response = requests.get("https://api.zrb.com/tasks", headers=headers)
```

**v2:**
```python
import requests

api_token = "your_v2_api_token"
headers = {"Authorization": f"Bearer {api_token}"}
response = requests.get("https://api.zrb.com/v2/tasks", headers=headers)
```

### 3. Task ID Type Change (Integer to UUID)

Task identifiers (`id`) have changed from integers to UUID strings. This provides greater flexibility and uniqueness for task identification.

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

**Example (Accessing task by ID):**

**v1:**
```python
task_id = 42
response = requests.get(f"https://api.zrb.com/tasks/{task_id}", headers=v1_headers)
```

**v2:**
```python
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890" # Example UUID
response = requests.get(f"https://api.zrb.com/v2/tasks/{task_id}", headers=v2_headers)
```

### 4. Task Field Renamed: `done` to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`.

**Before (v1 Task Object):**
```json
{
  "id": 42,
  "title": "Finish report",
  "done": true
}
```

**After (v2 Task Object):**
```json
{
  "id": "...",
  "title": "Finish report",
  "completed": true
}
```

**Example (Updating task status):**

**v1:**
```python
task_id = 42
payload = {"done": True}
response = requests.put(f"https://api.zrb.com/tasks/{task_id}", json=payload, headers=v1_headers)
```

**v2:**
```python
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
payload = {"completed": True}
response = requests.put(f"https://api.zrb.com/v2/tasks/{task_id}", json=payload, headers=v2_headers)
```

### 5. Task Creation Requires `project_id`

When creating a new task, you must now specify a `project_id`. Tasks cannot exist independently of a project in v2. Omitting `project_id` will result in an HTTP 422 Unprocessable Entity error.

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

**Example (Creating a task):**

**v1:**
```python
payload = {"title": "Draft proposal"}
response = requests.post("https://api.zrb.com/tasks", json=payload, headers=v1_headers)
```

**v2:**
```python
payload = {
  "title": "Draft proposal",
  "project_id": "proj_abc123" # Replace with your project ID
}
response = requests.post("https://api.zrb.com/v2/tasks", json=payload, headers=v2_headers)
```

### 6. List Endpoints Return Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response wrapped in an envelope object, rather than a bare array of items. This includes `total` and `next_cursor` fields for easier pagination.

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
    {"id": "...", "title": "Ship v2", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>` in the query parameters. You can also specify a `limit` parameter.

**Example (Fetching tasks):**

**v1:**
```python
response = requests.get("https://api.zrb.com/tasks", headers=v1_headers)
tasks = response.json()
for task in tasks:
    print(task["title"])
```

**v2:**
```python
response = requests.get("https://api.zrb.com/v2/tasks", headers=v2_headers)
paginated_response = response.json()
tasks = paginated_response["items"]
for task in tasks:
    print(task["title"])

# To get the next page
if paginated_response.get("next_cursor"):
    next_cursor = paginated_response["next_cursor"]
    response = requests.get(f"https://api.zrb.com/v2/tasks?cursor={next_cursor}", headers=v2_headers)
    next_page_tasks = response.json()["items"]
```

## Migration Checklist

1.  [ ] **Update CLI:** Upgrade your Zrb CLI to the latest v2 version.
2.  [ ] **Adjust Endpoint Paths:** Prefix all Zrb API calls with `/v2/`.
3.  [ ] **Refactor Authentication:** Change `X-Auth-Token` to `Authorization: Bearer <your_api_token>` in all API requests.
4.  [ ] **Handle Task ID Type:** Update any code that stores or processes task IDs to expect UUID strings instead of integers.
5.  [ ] **Rename Task Field:** Replace all references to the `done` field with `completed` in your code.
6.  [ ] **Provide `project_id` for Task Creation:** Ensure all task creation requests include a `project_id`.
7.  [ ] **Adapt to Paginated Responses:** Modify code that consumes list endpoints to correctly parse the `items` array from the new paginated envelope structure. Implement logic for handling `next_cursor` for full pagination.
8.  [ ] **Thoroughly Test:** Run your application's test suite and manually verify all Zrb CLI interactions.

## Upgrade Command

To upgrade your Zrb CLI installation to v2, run the following command:

```bash
zrb upgrade --to v2
```
