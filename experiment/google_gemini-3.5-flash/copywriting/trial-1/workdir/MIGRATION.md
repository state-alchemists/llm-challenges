# Zrb CLI v2 Migration Guide

This guide helps developers migrate their integrations and clients from the Zrb Task API v1 to v2. 

v2 introduces projects, standardized token-based authentication, improved pagination, and robust UUID identifiers. Because of these changes, v1 clients are not compatible with v2 endpoints. 

---

## Summary of Breaking Changes

The Zrb Task API v2 includes the following six breaking changes:

1. [API Endpoint Path Prefix Addition](#1-api-endpoint-path-prefix-addition)
2. [Authentication Header Format Update](#2-authentication-header-format-update)
3. [Task Identifier (`id`) Data Type Change (Integer to UUID)](#3-task-identifier-id-data-type-change-integer-to-uuid)
4. [Task Status Field Renamed (`done` to `completed`)](#4-task-status-field-renamed-done-to-completed)
5. [Mandatory `project_id` on Task Creation](#5-mandatory-project_id-on-task-creation)
6. [Paginated List Response Envelope (Bare Array to Object JSON)](#6-paginated-list-response-envelope-bare-array-to-object-json)

---

## Breaking Changes Detail

### 1. API Endpoint Path Prefix Addition

All endpoint paths are now version-prefixed with `/v2/`. Any requests sent to the legacy root paths without the version prefix will no longer reach the Task API endpoints.

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

### 2. Authentication Header Format Update

The custom authentication header `X-Auth-Token` has been replaced by the industry-standard `Authorization` Bearer token header. Sending requests with the `X-Auth-Token` header in v2 returns an HTTP `401 Unauthorized` status.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_v1_api_key
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_v2_api_token
```

---

### 3. Task Identifier (`id`) Data Type Change (Integer to UUID)

The task identifier `id` has changed from an auto-assigned integer to a globally unique UUIDv4 string. Client databases, variables, and path parameter validations must be updated to support 36-character string identifiers.

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

### 4. Task Status Field Renamed (`done` to `completed`)

The boolean field representing the task's completion status has been renamed from `done` to `completed`. This applies to task representation objects returned by the API as well as partial payloads submitted in `PUT` update requests.

#### Before (v1)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Mandatory `project_id` on Task Creation

v2 introduces multi-project workspaces. All tasks must belong to a specific project. Consequently, when creating a task with `POST /v2/tasks`, you must supply a non-empty `project_id` string. Omitting this field will result in an HTTP `422 Unprocessable Entity` response.

#### Before (v1)
```json
{
  "title": "New task title"
}
```

#### After (v2)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Response Envelope (Bare Array to Object JSON)

The list endpoint `GET /v2/tasks` no longer returns a bare JSON array. To support cursor-based pagination, it returns a paginated JSON envelope containing an `items` array, a `total` count, and a `next_cursor` string. Client-side deserializers expecting a bare array will fail and must be updated.

#### Before (v1)
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
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

#### After (v2)
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "e9f8d7c6-b5a4-3210-9fe8-d7c6b5a43210",
      "title": "Ship v1",
      "completed": true,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Step-by-Step Migration Checklist

Follow these steps to upgrade your clients and integrations:

- [ ] **Step 1: Upgrade CLI/SDK package.** Run the update command to fetch the v2 package.
- [ ] **Step 2: Prepend `/v2/` to all API paths.** Update your route constants or client base paths from `/tasks` to `/v2/tasks`.
- [ ] **Step 3: Update authentication headers.** Replace `X-Auth-Token: <token>` with `Authorization: Bearer <token>` across your request configurations.
- [ ] **Step 4: Update task model schemas.**
  - Change `id` types from integer to 36-character UUID strings.
  - Rename the `done` boolean field to `completed`.
  - Add the `project_id` string field.
- [ ] **Step 5: Provide `project_id` on creation.** Modify all task-creation logic to supply the required `project_id` string in `POST` request bodies.
- [ ] **Step 6: Refactor list endpoint parsers.** Adjust deserializers for `GET /v2/tasks` to read items from the `.items` property rather than the root JSON element, and integrate cursor-based pagination loop handling with `.next_cursor`.
- [ ] **Step 7: Run integration tests.** Validate the migrated client against a v2 staging environment to ensure all HTTP statuses and response mappings are correct.

---

## Upgrade Command

To update the Zrb CLI/SDK package to the latest version, run the following command:

```bash
pip install --upgrade zrb
```
