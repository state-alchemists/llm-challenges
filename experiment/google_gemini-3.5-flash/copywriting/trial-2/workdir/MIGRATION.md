# Zrb CLI v2 Migration Guide

This guide describes the breaking changes introduced in Zrb CLI v2 and provides instructions on how to migrate your existing v1 integrations to v2.

## Overview

Zrb v2 introduces support for projects, improved pagination, and stricter authentication mechanisms. Because of these new features, several v1 endpoints, data structures, and fields have changed or been deprecated.

---

## Breaking Changes

### 1. Endpoint Path Prefixing

All API endpoints are now prefixed with `/v2/` to support API versioning.

#### Before (v1)
Endpoints were accessible directly at the root path:
```http
GET /tasks
GET /tasks/1
```

#### After (v2)
All requests must be routed through the `/v2/` path prefix:
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header

The authentication mechanism has changed from a custom token header to a standard Bearer token header.

- **v1 Header:** `X-Auth-Token: <your_api_key>`
- **v2 Header:** `Authorization: Bearer <your_api_token>`

> **Note:** Sending requests with `X-Auth-Token` to v2 endpoints will result in an `HTTP 401 Unauthorized` response.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: my_api_key_123
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer my_api_token_123
```

---

### 3. Task ID Type Change (Integer to UUID)

The `id` field for task objects has been changed from an auto-incrementing integer to a UUID string to prevent ID enumeration and support decentralized ID generation.

- **v1 ID:** `42` (integer)
- **v2 ID:** `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"` (UUID string)

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

### 4. Field Rename: `done` to `completed`

The `done` boolean field on the task object has been renamed to `completed` to align with modern API conventions. This change affects both the response payloads and the write payloads (e.g., `PUT` requests).

#### Before (v1)
```json
// PUT /tasks/42
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2)
```json
// PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Mandatory `project_id` on Task Creation

With the introduction of Projects in v2, every task must now belong to a project. The `project_id` field is now **required** when creating tasks.

> **Warning:** Creating a task without a `project_id` in v2 will fail and return an `HTTP 422 Unprocessable Entity` response.

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

### 6. Paginated List Response

The task listing endpoint (`GET /v2/tasks`) now returns a paginated JSON envelope instead of a bare JSON array. This change improves client-side performance and prevents large response payloads.

The list endpoint now supports the following query parameters:
- `cursor` — Pagination cursor (optional)
- `limit` — Maximum results per page (optional, default `20`)

To fetch the next page of results, pass the returned `next_cursor` as the `cursor` query parameter.

#### Before (v1)
```http
GET /tasks
```
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
```http
GET /v2/tasks?limit=2
```
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
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Step-by-Step Migration Checklist

Follow these steps to upgrade your system from Zrb v1 to v2:

1. **Update Authentication**: Replace any occurrences of the `X-Auth-Token` header with `Authorization: Bearer <your_api_token>` in your API client code.
2. **Prepend Path Prefixes**: Update all API endpoint URLs from `/tasks...` to `/v2/tasks...`.
3. **Refactor ID Data Types**: Update your database schemas and code to store and process Task `id` values as UUID strings rather than integers.
4. **Rename Done Field**: Search-and-replace all client usages of the `.done` field on Task objects with `.completed`. Be sure to update both response parsing logic and `PUT` update request payloads.
5. **Implement Project ID Association**: Ensure that all task creation (`POST /v2/tasks`) code paths explicitly pass a valid `project_id` in the request body.
6. **Update List Pagination Handler**: Modify your task listing client code to parse the JSON envelope instead of a bare array. Read from the `.items` array, and implement cursor-based pagination using the `.next_cursor` field and the `?cursor=` query parameter.
7. **Test Integration**: Run integration tests to verify that no `HTTP 401`, `HTTP 404`, or `HTTP 422` errors are returned by the v2 endpoints.
8. **Upgrade the Zrb CLI**: Upgrade your local installation using the CLI upgrade command.

---

## Upgrade Command

To upgrade the Zrb CLI to version 2, run the following command in your terminal:

```bash
pip install --upgrade zrb
```
