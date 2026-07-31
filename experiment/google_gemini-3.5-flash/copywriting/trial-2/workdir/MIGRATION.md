# Zrb CLI v2 Migration Guide

Zrb CLI v2 is here! This major release introduces several powerful new features—including first-class projects, cursor-based pagination for larger datasets, and standard bearer token authentication. 

To support these improvements, we have introduced several breaking changes. This guide will walk you through migrating your integrations and codebases from Zrb v1 to v2.

---

## Table of Contents
1. [Breaking Changes](#breaking-changes)
   - [1. Endpoint Path Prefixing (`/v2/`)](#1-endpoint-path-prefixing-v2)
   - [2. Authentication Header Format](#2-authentication-header-format)
   - [3. Task ID Data Type (Integer to UUID)](#3-task-id-data-type-integer-to-uuid)
   - [4. Renaming Task `done` to `completed`](#4-renaming-task-done-to-completed)
   - [5. Mandatory `project_id` on Task Creation](#5-mandatory-project_id-on-task-creation)
   - [6. Paginated Envelope for List Endpoints](#6-paginated-envelope-for-list-endpoints)
2. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
3. [Upgrade Command](#upgrade-command)

---

## Breaking Changes

### 1. Endpoint Path Prefixing (`/v2/`)
All API endpoints are now prefixed with `/v2/` to support version co-existence and future APIs. Calling v1 style endpoints without the `/v2/` prefix will result in standard HTTP 404 errors or target deprecated v1 behavior.

#### Before (v1)
```http
GET /tasks
POST /tasks
GET /tasks/12
```

#### After (v2)
```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header Format
To align with standard API practices, Zrb v2 has migrated from a custom header (`X-Auth-Token`) to the standard `Authorization` Bearer token header. Requests targeting v2 with the old `X-Auth-Token` header will fail with HTTP 401 Unauthorized.

#### Before (v1)
```http
GET /tasks HTTP/1.1
X-Auth-Token: secret_api_key_12345
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer secret_api_token_12345
```

---

### 3. Task ID Data Type (Integer to UUID)
Task identifiers (`id`) have been upgraded from simple auto-assigned integers to globally unique UUID strings. This avoids ID collisions and enables safer client-side generation. Ensure your data schemas, model parsers, and URL path-parameter validators are updated to handle UUID strings rather than integers.

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

### 4. Renaming Task `done` to `completed`
The boolean field `done` has been renamed to `completed` for improved clarity and grammatical consistency. This change affects Task representations returned from all endpoints and must be updated in update requests (`PUT`) and client-side models.

#### Before (v1 PUT Request & Response)
```http
PUT /tasks/42 HTTP/1.1
Content-Type: application/json

{
  "done": true
}
```

#### After (v2 PUT Request & Response)
```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Content-Type: application/json

{
  "completed": true
}
```

---

### 5. Mandatory `project_id` on Task Creation
Tasks are now associated with a Project. Consequently, creating a task (`POST /v2/tasks`) now requires passing a valid string `project_id` in the request body. Omitting this field in v2 will result in an HTTP 422 Unprocessable Entity error.

#### Before (v1 POST Request)
```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

#### After (v2 POST Request)
```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Envelope for List Endpoints
List endpoints such as `GET /v2/tasks` no longer return a bare JSON array. To support cursor-based pagination for scalability, they now return a paginated envelope object. The array of items is nested under the `items` key, and pagination metadata is provided via `total` and `next_cursor`.

To fetch subsequent pages, pass the returned `next_cursor` as a `cursor` query parameter: `GET /v2/tasks?cursor=<next_cursor>`.

#### Before (v1 Response)
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

#### After (v2 Response)
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
      "created_at": "2024-01-15T10:30:15Z"
    }
  ],
  "total": 2,
  "next_cursor": null
}
```

---

## Step-by-Step Migration Checklist

Follow these steps to upgrade your application and integrations smoothly:

- [ ] **Update URL Paths:** Prepend `/v2` to all Zrb CLI API endpoints in your API clients and routing configuration.
- [ ] **Modify Authentication Headers:** Replace `X-Auth-Token: <token>` with `Authorization: Bearer <token>` in all client request wrappers.
- [ ] **Change ID Field Handling:** Update your schemas, ORMs, and frontend models to treat task `id` as a string (UUID) rather than an integer.
- [ ] **Rename Status Fields:** Search your codebase for references to `.done` (or JSON key `"done"`) and rename them to `.completed` (JSON key `"completed"`).
- [ ] **Incorporate Project Associations:** Ensure every part of your app that creates a task retrieves and provides a valid `project_id` in the `POST` payload.
- [ ] **Refactor List Handling:** Update your data fetching adapters to extract lists from the `.items` property of the response rather than treating the response itself as an array.
- [ ] **Implement Pagination:** Adapt your list views and infinite scroll/pagination components to use the `next_cursor` parameter with the `cursor` query parameter.
- [ ] **Run Integration Tests:** Verify end-to-end flows using the v2 endpoints.

---

## Upgrade Command

To update the Zrb CLI to the latest v2 version, run the following upgrade command in your terminal:

```bash
pip install --upgrade zrb
```
