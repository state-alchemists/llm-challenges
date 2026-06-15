# Zrb CLI v2 Migration Guide

Zrb CLI v2 introduces scoped projects, cursor-based pagination, and stricter authentication mechanisms. This guide is designed to help experienced developers transition their existing v1 integrations to the new v2 API smoothly.

---

## Table of Contents

- [Breaking Changes Summary](#breaking-changes-summary)
- [Detailed Breaking Changes & Examples](#detailed-breaking-changes--examples)
  1. [Endpoint Prefix Changed to `/v2/`](#1-endpoint-prefix-changed-to-v2)
  2. [Authentication Header Changed](#2-authentication-header-changed)
  3. [Task ID Type Changed from Integer to UUID String](#3-task-id-type-changed-from-integer-to-uuid-string)
  4. [Task Field `done` Renamed to `completed`](#4-task-field-done-renamed-to-completed)
  5. [Task Creation Now Requires `project_id`](#5-task-creation-now-requires-project_id)
  6. [List Endpoints Return a Paginated Envelope](#6-list-endpoints-return-a-paginated-envelope)
- [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
- [Upgrade Command](#upgrade-command)

---

## Breaking Changes Summary

Several core APIs, data types, and routing patterns have evolved in v2. Specifically, there are six breaking changes you must address when migrating from v1 to v2:

1. **Endpoint Prefixing**: All routes are now prefixed with `/v2/`.
2. **Authentication Header**: Changed from `X-Auth-Token` to standard `Authorization: Bearer`.
3. **Task ID Type**: Changed from auto-assigned integers to UUID strings.
4. **Task State Renaming**: Task boolean field `done` is renamed to `completed`.
5. **Project Scoping**: Task creation now strictly requires a `project_id` field.
6. **List Pagination**: List endpoints now return a paginated JSON envelope instead of a bare array.

---

## Detailed Breaking Changes & Examples

### 1. Endpoint Prefix Changed to `/v2/`

All endpoints are now prefixed with `/v2/` to allow side-by-side versioning and future-proofing. Legacy v1 endpoints (e.g., `/tasks`) are no longer available in the v2 API service.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
```

---

### 2. Authentication Header Changed

To adhere to industry standards and improve security, custom auth headers are deprecated. You must use the `Authorization` header with a `Bearer` token. Requests sent to v2 endpoints with the old `X-Auth-Token` header will fail with an **HTTP 401 Unauthorized** error.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key_v1
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token_v2
```

---

### 3. Task ID Type Changed from Integer to UUID String

To prevent ID conflicts and improve security across distributed systems, Task `id`s have transitioned from integers to standard UUID strings. Ensure your database schemas, internal data representations, and client routers are updated to accept string UUIDs.

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

### 4. Task Field `done` Renamed to `completed`

The boolean state flag `done` has been renamed to `completed`. This change affects task schema representation and write payloads when updating a task status.

#### Before (v1)
```json
// Update task request (PUT /tasks/42)
{
  "done": true
}
```

#### After (v2)
```json
// Update task request (PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890)
{
  "completed": true
}
```

---

### 5. Task Creation Now Requires `project_id`

Every task in v2 is part of a scoped project. When migrating to the `/v2/tasks` endpoint, the `project_id` field is now strictly required inside the task creation request payload. Submitting a task creation request without a valid `project_id` returns an **HTTP 422 Unprocessable Entity** error.

#### Before (v1)
```http
POST /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key_v1
Content-Type: application/json

{
  "title": "New task title"
}
```

#### After (v2)
```http
POST /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token_v2
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Endpoints Return a Paginated Envelope

To safeguard performance when rendering large task collections, list endpoints no longer return a bare array. The response is now a paginated envelope containing list items, a total item count, and a cursor identifier. 

You can pass `?cursor=<next_cursor>` and `?limit=<max_items>` (default `20`) to step through results.

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
    }
  ],
  "total": 12,
  "next_cursor": "cursor_xyz123"
}
```

---

## Step-by-Step Migration Checklist

Follow these checklist items to ensure a successful transition to v2:

- [ ] **Endpoint Updates**: Modify base URLs of your API connections to target `/v2/` prefixes.
- [ ] **Credential Refactoring**: Replace all occurrences of `X-Auth-Token` header key and inject standard `Authorization: Bearer <token>` in your request middleware.
- [ ] **ID Type Cast Alterations**: Adjust models, schemas, and parsers from integers to accept UUID strings for task ID identifiers.
- [ ] **Attribute Mapper Synchronization**: Update serializer and client payload properties from `done` to `completed`.
- [ ] **Workspace/Project Binding**: Map existing task items into distinct projects or retrieve a valid active `project_id` to include when creating new tasks.
- [ ] **Collection Unpacking**: Update loops and mapping processes that consume the list endpoint to navigate through the `items` list of the response envelope, and configure pagination logic using `cursor` and `limit` properties.
- [ ] **Local Verification**: Run all unit and integration tests against your local or staging v2 API instances to ensure clean endpoints execution.

---

## Upgrade Command

To complete your upgrade, update the Zrb CLI to the latest v2 version.

If you installed Zrb via **pip**:
```bash
pip install --upgrade zrb
```

If you installed Zrb via **pipx**:
```bash
pipx upgrade zrb
```
