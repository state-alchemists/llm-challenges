# Zrb Task API v2 Migration Guide

This guide describes how to upgrade your applications and integrations from the Zrb Task API v1 to v2. 

Zrb v2 introduces native project support, improved cursor-based pagination, and stricter security protocols. This release contains several breaking changes to authentication, data schemas, and endpoint responses.

---

## Table of Contents
1. [Breaking Changes](#breaking-changes)
   - [1. Endpoint Path Prefix (`/v2/`)](#1-endpoint-path-prefix-v2)
   - [2. Authentication Header (`Authorization: Bearer`)](#2-authentication-header-authorization-bearer)
   - [3. Task ID Data Type (UUID String)](#3-task-id-data-type-uuid-string)
   - [4. Task Completion Field Name (`completed`)](#4-task-completion-field-name-completed)
   - [5. Task Creation Requirement (`project_id`)](#5-task-creation-requirement-project_id)
   - [6. List Endpoint Response Envelope (Pagination)](#6-list-endpoint-response-envelope-pagination)
2. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
3. [Upgrade Command](#upgrade-command)

---

## Breaking Changes

### 1. Endpoint Path Prefix (`/v2/`)
All endpoints are now scoped under the `/v2/` path prefix. Requests sent to v1 paths (without `/v2/`) will fail or yield legacy v1 behavior.

#### Before (v1)
```http
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

#### After (v2)
```http
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication Header (`Authorization: Bearer`)
The custom `X-Auth-Token` header has been replaced by the standard `Authorization` header using the `Bearer` scheme. Requests attempting to use the old header will be rejected with an `HTTP 401 Unauthorized` response.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token
```

---

### 3. Task ID Data Type (UUID String)
The task identifier (`id`) has changed from an auto-assigned integer to a UUIDv4 string. Update client-side parsers, type systems, and database schemas storing these IDs to use string/UUID types rather than integers.

#### Before (v1 Response)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2 Response)
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

### 4. Task Completion Field Name (`completed`)
The boolean task completion field has been renamed from `done` to `completed`. This change affects both task retrieval structures and fields accepted during a task update (`PUT`).

#### Before (v1 PUT Request & Response)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2 PUT Request & Response)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task Creation Requirement (`project_id`)
Tasks can no longer be created in isolation. All tasks must belong to a project. Consequently, when creating a task via `POST /v2/tasks`, you must specify a valid `project_id`. Requests omitting `project_id` will fail with an `HTTP 422 Unprocessable Entity` response.

#### Before (v1 POST Request)
```json
{
  "title": "New task title"
}
```

#### After (v2 POST Request)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Endpoint Response Envelope (Pagination)
To support scale and efficient querying, list endpoints no longer return a bare JSON array. They now return a paginated envelope object containing an `items` list, a `total` count, and a `next_cursor` string for pagination. You can control pagination using the optional `cursor` and `limit` query parameters.

#### Before (v1 GET /tasks Response)
```json
[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:30:00Z"
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

Follow these steps to migrate your code integration from v1 to v2:

- [ ] **1. Upgrade SDK and CLI Dependencies**
  Upgrade your client SDKs and the local Zrb CLI installation to support v2 commands and schemas.
- [ ] **2. Rotate and Reformat Credentials**
  Generate a new API token if necessary, and prepare to transition authentication keys to Bearer token format.
- [ ] **3. Update Client Authentication Headers**
  Modify your API client or HTTP request builder configuration to use the `Authorization: Bearer <token>` header instead of the legacy `X-Auth-Token: <token>` header.
- [ ] **4. Update Endpoint Paths**
  Append `/v2` to your base URL or update individual routes in your configuration to point to `/v2/tasks` rather than `/tasks`.
- [ ] **5. Refactor ID Handling**
  Change any database columns, data models, or variables representing task IDs from integers to strings (or UUID specific types) to prevent type assertion or constraint errors.
- [ ] **6. Map `done` to `completed`**
  Perform a search-and-replace in your codebase to update properties from `done` to `completed` on task payloads, form mappings, and JSON serializers/deserializers.
- [ ] **7. Update Task Creation Flows**
  Locate your task creation functions and ensure they fetch/provide a valid `project_id` when invoking `POST /v2/tasks`.
- [ ] **8. Refactor List Parsing Logic**
  Update response-handling logic for listing tasks. Ensure your application parses the task list from the `items` key of the response envelope rather than expecting a bare root-level JSON array.
- [ ] **9. Implement Cursor Pagination**
  Integrate pagination workflows by reading `next_cursor` and passing it as a `cursor` query parameter to successive `GET /v2/tasks` calls when traversing task pages.
- [ ] **10. Run Tests and Validate**
  Run your unit and integration test suites against a staging or test Zrb v2 environment to verify that all operations are working correctly.

---

## Upgrade Command

To update your local Zrb CLI tool to v2, run the following command:

```bash
pip install --upgrade zrb
```
