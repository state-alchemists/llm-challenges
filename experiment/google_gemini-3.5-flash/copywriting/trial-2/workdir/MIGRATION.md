# Zrb Task API — v1 to v2 Migration Guide

This migration guide helps developers upgrade their integrations from the Zrb Task API v1 to v2. The v2 release introduces native project support, improved Cursor-based pagination, and stricter authentication mechanisms.

---

## Table of Contents
1. [Endpoint Path Prefix Changes](#1-endpoint-path-prefix-changes)
2. [Authentication Header Update](#2-authentication-header-update)
3. [Task ID Type Change (Integer to UUID)](#3-task-id-type-change-integer-to-uuid)
4. [Task Field Rename (`done` to `completed`)](#4-task-field-rename-done-to-completed)
5. [Mandatory `project_id` on Task Creation](#5-mandatory-project_id-on-task-creation)
6. [Paginated Response Envelope](#6-paginated-response-envelope)
7. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
8. [Upgrade CLI Command](#upgrade-cli-command)

---

## Breaking Changes

### 1. Endpoint Path Prefix Changes
All task endpoints in v2 are now prefixed with `/v2/` to support API versioning. All requests to the old v1 endpoints without the prefix will return `HTTP 404 Not Found`.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.example.com
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.example.com
```

---

### 2. Authentication Header Update
The custom authentication header `X-Auth-Token` has been deprecated and replaced by the standard Bearer token `Authorization` header. Sending requests with `X-Auth-Token` to v2 endpoints will result in an `HTTP 401 Unauthorized` response.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.example.com
X-Auth-Token: your_api_key_here
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.example.com
Authorization: Bearer your_api_token_here
```

---

### 3. Task ID Type Change (Integer to UUID)
To improve security and support distributed systems, the task `id` field type has changed from an auto-incrementing integer to a UUID string. Please update your client schemas, type mappings (e.g., in TypeScript/Go), and local database column types accordingly.

#### Before (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 4. Task Field Rename (`done` to `completed`)
To align with standard industry vocabulary, the `done` boolean field on Task objects has been renamed to `completed`. 

*Note: This affects both retrieval and update payloads (`PUT /v2/tasks/{id}`).*

#### Before (v1)
```json
// PUT /tasks/42
{
  "done": true
}
```

#### After (v2)
```json
// PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{
  "completed": true
}
```

---

### 5. Mandatory `project_id` on Task Creation
All tasks must now belong to a project. When creating a task (`POST /v2/tasks`), you must supply a valid `project_id`. Omitting `project_id` will cause the server to reject the request with `HTTP 422 Unprocessable Entity`.

#### Before (v1)
```json
// POST /tasks
{
  "title": "New task title"
}
```

#### After (v2)
```json
// POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Response Envelope
In v1, retrieving the list of tasks returned a bare JSON array. In v2, listing tasks returns a paginated envelope object. The actual tasks array is nested under the `items` key, accompanied by pagination metadata. To fetch subsequent pages, use the `?cursor=<next_cursor>` query parameter.

#### Before (v1)
```json
// GET /tasks
[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

#### After (v2)
```json
// GET /v2/tasks
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

---

## Step-by-Step Migration Checklist

Follow these sequential steps to safely transition your integration to v2:

- [ ] **Step 1: Upgrade Zrb CLI**
  Upgrade your local environments, CI/CD pipelines, and runtime dependencies to use the v2 Zrb package.
- [ ] **Step 2: Update Authentication Headers**
  Change all task-related API requests to send the standard `Authorization: Bearer <your_api_token>` header instead of the deprecated `X-Auth-Token`.
- [ ] **Step 3: Update Request Endpoints**
  Prepend `/v2` to all of your endpoint request paths (e.g., map `/tasks` to `/v2/tasks`).
- [ ] **Step 4: Update ID Fields and Typings**
  Update your types and database schemas to expect a UUID string for the task `id` instead of an integer.
- [ ] **Step 5: Rename fields (`done` ➔ `completed`)**
  Search your codebase for all references to the `done` attribute on task objects and rename them to `completed`. Ensure you update any local parsing logic and PUT update requests.
- [ ] **Step 6: Integrate `project_id` into Task Creation**
  Modify your task creation forms or background tasks to pass the required `project_id` payload on `POST /v2/tasks`.
- [ ] **Step 7: Adopt Paginated List Responses**
  Refactor client-side task fetching to parse the paginated list envelope (`items`, `total`, `next_cursor`). Update list render functions to extract list arrays from `.items` rather than the root payload.
- [ ] **Step 8: Implement Cursor Pagination Support**
  Add pagination traversal logic that feeds the returned `next_cursor` back into the `GET /v2/tasks?cursor=` parameter for next-page requests.
- [ ] **Step 9: Run and Validate Integration Tests**
  Execute your test suite to ensure that no `HTTP 401`, `HTTP 404`, or `HTTP 422` errors are returned by the updated API.

---

## Upgrade CLI Command

To upgrade your Zrb CLI package to the latest version, run the following command in your terminal:

```bash
pip install --upgrade zrb
```
