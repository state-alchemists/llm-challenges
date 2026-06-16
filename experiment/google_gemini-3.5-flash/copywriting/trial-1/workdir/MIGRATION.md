# Zrb CLI v2 Migration Guide

Zrb v2 introduces support for multi-project scoping, improved pagination efficiency, and enhanced security standards. This guide details every breaking change from v1 and provides actionable instructions and code examples to assist with your migration.

---

## Breaking Changes Summary

1. [Endpoint Prefix Changes (`/v2/` prefix)](#1-endpoint-prefix-changes)
2. [Authentication Header Upgraded (`Authorization: Bearer`)](#2-authentication-header-upgraded)
3. [Task Identifier Type Migration (Integer to UUID)](#3-task-identifier-type-migration)
4. [Task Field Renamed (`done` to `completed`)](#4-task-field-renamed)
5. [Required `project_id` on Creation](#5-required-project_id-on-creation)
6. [Paginated Envelope Response for List Endpoints](#6-paginated-envelope-response-for-list-endpoints)

---

## Breaking Changes in Detail

### 1. Endpoint Prefix Changes

All endpoints are now version-controlled under the `/v2/` base path. Standard v1 paths without this prefix will return `HTTP 404 Not Found` or `HTTP 301 Moved Permanently` depending on server configuration.

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

### 2. Authentication Header Upgraded

The custom `X-Auth-Token` header has been deprecated in favor of the standard `Authorization: Bearer` token pattern. Any requests still utilizing `X-Auth-Token` will fail with an `HTTP 401 Unauthorized` status.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key_here
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token_here
```

---

### 3. Task Identifier Type Migration

To accommodate decentralized environments and eliminate ID enumeration vulnerabilities, task `id`s have transitioned from auto-assigned integers to UUID string representations.

You must migrate database columns/schemas, API client models, and routing logic from integer parsing to string/UUID formatting.

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

### 4. Task Field Renamed

The boolean field representing completion status has been renamed from `done` to `completed`. This change applies both to returned Task objects and update request bodies.

#### Before (v1)
```json
// Task Object field 'done'
{
  "id": 42,
  "title": "Write tests",
  "done": false
}

// Update Request Payload (PUT /tasks/42)
{
  "done": true
}
```

#### After (v2)
```json
// Task Object field 'completed'
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}

// Update Request Payload (PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890)
{
  "completed": true
}
```

---

### 5. Required `project_id` on Creation

All tasks in v2 must belong to a project. When creating a task, the `project_id` field is now **mandatory**. Omitting this field in the payload of a `POST` request results in an `HTTP 422 Unprocessable Entity` validation error.

#### Before (v1 Create Task)
```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

#### After (v2 Create Task)
```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Envelope Response for List Endpoints

List endpoints now return a standardized paginated envelope containing list items, total counts, and cursors. This replaces the v1 behavior which returned a bare JSON array.

#### Before (v1 Response from `GET /tasks`)
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
    "created_at": "2024-01-15T11:30:00Z"
  }
]
```

#### After (v2 Response from `GET /v2/tasks`)
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
      "id": "f8e7d6c5-b4a3-2109-8765-43210fedcba9",
      "title": "Ship v1",
      "completed": true,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T11:30:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page in v2, pass the `next_cursor` parameter:
```http
GET /v2/tasks?cursor=cursor_xyz&limit=2 HTTP/1.1
```

---

## Step-by-Step Migration Checklist

Follow these steps to safely migrate your integration from v1 to v2:

1. **[ ] Update Credentials & Header**: Swap your custom `X-Auth-Token` header logic to `Authorization: Bearer <your_api_token>` in all API clients.
2. **[ ] Migrate Database & Client Schemas**:
   - Update ID fields in schemas/models from `integer` to `string` (UUID).
   - Rename the `done` field or column to `completed`.
   - Add a `project_id` column (string, required) to task tables.
3. **[ ] Add Multi-project Context**: Update your frontend and client creation workflows to pass a valid `project_id` whenever sending `POST /v2/tasks` requests.
4. **[ ] Update API Request Endpoints**: Prepend all your Zrb API endpoint paths with `/v2/` (e.g., replace `/tasks` with `/v2/tasks`).
5. **[ ] Refactor List Parsing**: Rewrite JSON parser handlers that consume task lists to read from the `.items` property instead of asserting a bare top-level array.
6. **[ ] Implement Cursor Pagination**: Utilize the `.next_cursor` metadata returned from lists to navigate sequential pages instead of assuming page/offset limits.
7. **[ ] Run Integration Tests**: Execute validation suites on the updated codebase to ensure no legacy endpoints or structures remain.
8. **[ ] Upgrade the Zrb CLI**: Upgrade your local installation of the CLI tool to the latest v2 release.

---

## Upgrade Command

To update the Zrb CLI on your development machine or server, run:

```bash
pip install --upgrade zrb
```

*For global installations managed via pipx, run:*
```bash
pipx upgrade zrb
```
