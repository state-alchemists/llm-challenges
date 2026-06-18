# Zrb CLI v2 Migration Guide

Zrb CLI v2 introduces several breaking changes to improve performance, structure, security, and scalability. This guide covers all breaking changes, provides code comparison examples, and outlines a clear path to upgrade your applications.

---

## Table of Contents

1. [Breaking Changes](#breaking-changes)
   - [1. Endpoint Prefix Change (`/` to `/v2/`)](#1-endpoint-prefix-change--to-v2)
   - [2. Authentication Header Change (`X-Auth-Token` to `Bearer` Token)](#2-authentication-header-change-x-auth-token-to-bearer-token)
   - [3. Task ID Type Change (Integer to UUID String)](#3-task-id-type-change-integer-to-uuid-string)
   - [4. Task Field Renamed (`done` to `completed`)](#4-task-field-renamed-done-to-completed)
   - [5. Required `project_id` on Task Creation](#5-required-project_id-on-task-creation)
   - [6. Paginated List Envelope Response (Instead of Bare Array)](#6-paginated-list-envelope-response-instead-of-bare-array)
2. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
3. [Upgrade Zrb CLI Command](#upgrade-zrb-cli-command)

---

## Breaking Changes

### 1. Endpoint Prefix Change (`/` to `/v2/`)

All endpoint paths in v2 are now prefixed with `/v2/` to support API versioning. If you call the root path directly (e.g. `GET /tasks`), your requests will no longer route correctly.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.run
X-Auth-Token: your_api_key
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.run
Authorization: Bearer your_api_token
```

---

### 2. Authentication Header Change (`X-Auth-Token` to `Bearer` Token)

Security is now aligned with standard HTTP practices. The legacy `X-Auth-Token` header has been deprecated. Requests must now use the `Authorization: Bearer` header. 
*Note: Any request containing the old `X-Auth-Token` header will return an **HTTP 401 Unauthorized** error.*

#### Before (v1)
```http
POST /tasks HTTP/1.1
Host: api.zrb.run
X-Auth-Token: secret_api_key_v1
Content-Type: application/json

{
  "title": "Complete documentation"
}
```

#### After (v2)
```http
POST /v2/tasks HTTP/1.1
Host: api.zrb.run
Authorization: Bearer secret_api_token_v2
Content-Type: application/json

{
  "title": "Complete documentation",
  "project_id": "proj_abc123"
}
```

---

### 3. Task ID Type Change (Integer to UUID String)

To allow offline creation and prevent ID enumeration, the task `id` field is now a UUID string (version 4 format) instead of an auto-assigned integer. This affects all URL routing, database schemas, and clients expecting numerical IDs.

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

### 4. Task Field Renamed (`done` to `completed`)

The task's completion status field `done` (boolean) has been renamed to `completed`. 
*Note: Using `done` in `PUT` requests will be ignored or rejected, and incoming payloads will only expose `completed`.*

#### Before (v1 PUT Request)
```http
PUT /tasks/42 HTTP/1.1
Host: api.zrb.run
X-Auth-Token: secret_api_key_v1
Content-Type: application/json

{
  "done": true
}
```

#### After (v2 PUT Request)
```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Host: api.zrb.run
Authorization: Bearer secret_api_token_v2
Content-Type: application/json

{
  "completed": true
}
```

---

### 5. Required `project_id` on Task Creation

v2 introduces first-class multi-project support. Every task must belong to a project. The `project_id` field (string) is now a required parameter in the `POST` request payload.
*Note: Omitting `project_id` in v2 will trigger an **HTTP 422 Unprocessable Entity** error.*

#### Before (v1 POST Request Body)
```json
{
  "title": "Clean the kitchen"
}
```

#### After (v2 POST Request Body)
```json
{
  "title": "Clean the kitchen",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Envelope Response (Instead of Bare Array)

To handle growing lists of tasks efficiently, the task index endpoint `GET /v2/tasks` now returns a paginated envelope containing `items`, `total`, and a cursor-based pagination identifier `next_cursor` rather than a bare array. 
*Note: To fetch subsequent pages, pass `?cursor=<next_cursor>` in your URL query parameters.*

#### Before (v1 GET Response)
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "2024-01-15T10:30:00Z"},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "2024-01-15T10:30:00Z"}
]
```

#### After (v2 GET Response)
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

Follow these steps to safely migrate your integration from v1 to v2:

- [ ] **Database & Schemas**: Update task ID fields from integer to UUID string (UUIDv4) and rename the `done` boolean field to `completed`.
- [ ] **Project Setup**: Generate or locate project IDs (`project_id`) for your tasks, since all task creation now requires a project association.
- [ ] **Request Authentication**: Replace the custom HTTP header `X-Auth-Token: <your_api_key>` with the standard Bearer header: `Authorization: Bearer <your_api_token>`.
- [ ] **API Endpoint URIs**: Update all REST client URIs to point to the `/v2/` prefix (e.g. change `/tasks` to `/v2/tasks`).
- [ ] **Payload Schema Updates**:
  - For **Task Creation (`POST /v2/tasks`)**: Add the required `project_id` field.
  - For **Task Modification (`PUT /v2/tasks/{id}`)**: Replace the `done` key with `completed`.
- [ ] **Response Handlers**: Modify list parsing logic to extract items from the `"items"` array of the paginated envelope (`data.items`) instead of expecting a bare array response. Implement cursor-based pagination using the `"next_cursor"` value if necessary.
- [ ] **Local Testing**: Run integration tests to ensure that no `401` or `422` status codes are encountered.

---

## Upgrade Zrb CLI Command

To upgrade the Zrb CLI to the latest version featuring the v2 API capabilities, run the following command:

```bash
pip install --upgrade zrb
```

Verify that the installation was successful and is on version 2:

```bash
zrb version
```
