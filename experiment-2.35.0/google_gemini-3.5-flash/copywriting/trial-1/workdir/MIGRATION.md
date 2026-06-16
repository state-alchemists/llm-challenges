# Zrb Task API — v2 Migration Guide

Welcome to the Zrb Task API v2 migration guide. This major release introduces several new features, including projects, improved cursor-based pagination, and stricter security protocols.

This document details all breaking changes between v1 and v2, provides comparison examples, and outlines a step-by-step checklist to help you migrate your applications smoothly.

---

## Table of Contents
1. [Breaking Changes Summary](#breaking-changes-summary)
2. [Detailed Breaking Changes](#detailed-breaking-changes)
   - [1. Endpoint URL Paths (/v2/ Prefix)](#1-endpoint-url-paths-v2-prefix)
   - [2. Authentication Header](#2-authentication-header)
   - [3. Task ID Data Type (Integer to UUID)](#3-task-id-data-type-integer-to-uuid)
   - [4. Task Field Renamed (done to completed)](#4-task-field-renamed-done-to-completed)
   - [5. Mandatory Project Association (project_id)](#5-mandatory-project-association-project_id)
   - [6. Paginated Envelope for List Endpoints](#6-paginated-envelope-for-list-endpoints)
3. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
4. [Upgrade Command](#upgrade-command)

---

## Breaking Changes Summary

| Breaking Change | v1 Specification | v2 Specification |
| :--- | :--- | :--- |
| **Endpoint Prefix** | `/tasks` | `/v2/tasks` |
| **Auth Header** | `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` |
| **Task ID Type** | `integer` (e.g., `42`) | `string` (UUIDv4) |
| **Status Field** | `done` (boolean) | `completed` (boolean) |
| **Creation Requirements** | Only `title` is required | `title` and `project_id` are required |
| **List Responses** | Bare JSON array (`[...]`) | Paginated envelope (`{"items": [...], ...}`) |

---

## Detailed Breaking Changes

### 1. Endpoint URL Paths (/v2/ Prefix)

All endpoints have been updated with the versioned prefix `/v2/` to ensure better API lifecycle management. Old non-prefixed paths will return HTTP 404.

#### Before (v1)
```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

#### After (v2)
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header

For enhanced security, Zrb v2 adopts the standard OAuth2 Bearer token schema. The custom header `X-Auth-Token` is deprecated. Requests sending `X-Auth-Token` to v2 endpoints will be rejected with `HTTP 401 Unauthorized`.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: my_secret_api_key_v1
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer my_secret_api_token_v2
```

---

### 3. Task ID Data Type (Integer to UUID)

To support decentralized generation and avoid collisions, task identifiers are now unique, non-sequential UUID strings rather than auto-incrementing integers. You must update your models, schemas, and routing parameter types accordingly.

#### Before (v1 Task Object)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2 Task Object)
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

### 4. Task Field Renamed (done to completed)

The task boolean status field `done` is renamed to `completed` for semantic consistency with the API's verb conventions. Any references to `done` in request bodies (such as task updates) or client-side JSON deserialization models must be renamed to `completed`.

#### Before (v1 PUT Request Body)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2 PUT Request Body)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Mandatory Project Association (project_id)

Tasks must now belong to a project. When creating a task, you must supply a string `project_id` in the request body. Creating a task without a `project_id` returns an `HTTP 422 Unprocessable Entity` status code.

#### Before (v1 POST Request Body)
```json
{
  "title": "New task title"
}
```

#### After (v2 POST Request Body)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Envelope for List Endpoints

List endpoints now return a JSON envelope with pagination metadata instead of returning a raw, unpaginated JSON array. This prevents performance bottlenecks on large datasets.

To fetch subsequent pages, read the returned `next_cursor` value and pass it as a `cursor` query parameter on the next request.

#### Before (v1 GET /tasks Response)
```json
[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:30:00Z"
  },
  {
    "id": 2,
    "title": "Ship v1",
    "done": true,
    "created_at": "2024-01-15T10:31:00Z"
  }
]
```

#### After (v2 GET /v2/tasks Response)
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

---

## Step-by-Step Migration Checklist

Follow these steps to upgrade your application integration from Zrb v1 to v2:

- [ ] **Step 1: Update Auth Configurations**
  - Locate all API clients in your codebase.
  - Replace the custom `X-Auth-Token` header definition with the standard `Authorization: Bearer <token>` header.
- [ ] **Step 2: Update Data Model Schemas**
  - Change the type of task `id` fields from `integer` to `string` / `UUID`.
  - Rename the task `done` field (boolean) to `completed`.
  - Add `project_id` (string) as a required field in your task schema definitions.
- [ ] **Step 3: Refactor Endpoint URLs**
  - Update base path strings for all task endpoints by inserting the `/v2/` prefix.
- [ ] **Step 4: Update Create Task Requests**
  - Modify all `POST` payload generation logic to include a valid, non-empty `project_id` string parameter.
- [ ] **Step 5: Adopt Pagination Parsing**
  - Locate any code reading from `GET /tasks`.
  - Refactor the response processing to read the items list from the `items` property of the returned JSON envelope instead of treating the response payload as a raw array.
  - (Optional) Implement client-side support for cursor-based pagination by querying `/v2/tasks?cursor=<next_cursor>`.
- [ ] **Step 6: Run Tests and Validate**
  - Run integration tests to ensure that all HTTP requests successfully target the `/v2/` prefix and that responses are parsed correctly.

---

## Upgrade Command

To upgrade the Zrb CLI on your development environment or within your CI/CD runner environments, execute the appropriate upgrade command:

```bash
# Upgrade via pip (standard python environment)
pip install --upgrade zrb

# Or upgrade via pipx (recommended)
pipx upgrade zrb
```
