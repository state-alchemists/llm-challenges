# Zrb CLI v2 Migration Guide

Zrb CLI v2 introduces projects, improved pagination, and stricter authentication. These changes make the API more robust but introduce several breaking changes that are incompatible with v1. 

This guide details all breaking changes and provides before/after examples to assist you in migrating your client integrations.

---

## Table of Breaking Changes

1. [Endpoint Paths Prefixed with `/v2/`](#1-endpoint-paths-prefixed-with-v2)
2. [Authentication Header Migration](#2-authentication-header-migration)
3. [Task ID Type Changed from Integer to UUID](#3-task-id-type-changed-from-integer-to-uuid)
4. [Task Field Renamed (`done` to `completed`)](#4-task-field-renamed-done-to-completed)
5. [Required `project_id` Field for Task Creation](#5-required-project_id-field-for-task-creation)
6. [Paginated Envelope Response for List Endpoints](#6-paginated-envelope-response-for-list-endpoints)

---

## Breaking Changes Details

### 1. Endpoint Paths Prefixed with `/v2/`

All endpoint routes are now prefixed with `/v2/` to support version co-existence and API versioning.

#### Before
```http
GET /tasks
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

#### After
```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication Header Migration

The authentication mechanism has changed from a custom `X-Auth-Token` header to standard Bearer token authorization. Legacy `X-Auth-Token` headers will now return `HTTP 401 Unauthorized`.

#### Before
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: v1_secret_api_key_12345
```

#### After
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer v2_secret_api_token_67890
```

---

### 3. Task ID Type Changed from Integer to UUID

To support scalable ID generation and prevent enumeration, the Task `id` is now a 36-character UUID string rather than an auto-assigned integer. Clients must update internal schemas, databases, and type systems.

#### Before (Task Object)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (Task Object)
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

The boolean attribute tracking task completion status has been renamed from `done` to `completed`. This change affects both task retrieval payloads and update request bodies.

#### Before (Task Update Request)
```http
PUT /tasks/42 HTTP/1.1
Content-Type: application/json

{
  "title": "Updated title",
  "done": true
}
```

#### After (Task Update Request)
```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Content-Type: application/json

{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required `project_id` Field for Task Creation

All tasks in v2 must belong to a parent project. The field `project_id` is now **required** in the payload when creating a task. Omitting `project_id` returns `HTTP 422 Unprocessable Entity`.

#### Before (Task Creation)
```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

#### After (Task Creation)
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

The List Tasks endpoint no longer returns a bare array. It now returns an object container enclosing the items along with cursor pagination metadata. Clients must unpack the envelope and use `next_cursor` to fetch subsequent pages via the `?cursor=<next_cursor>` query parameter.

#### Before (List Tasks Response)
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
    "created_at": "2024-01-15T10:35:00Z"
  }
]
```

#### After (List Tasks Response)
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
      "created_at": "2024-01-15T10:35:00Z"
    }
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your codebase to v2:

- [ ] **Upgrade your installation**: Update the Zrb CLI to the latest release using the command below.
- [ ] **Update Auth Headers**: Replace all `X-Auth-Token` headers with the `Authorization: Bearer <your_api_token>` standard.
- [ ] **Change Base Paths**: Prepend `/v2/` to all API endpoint route paths.
- [ ] **Migrate IDs to UUID**: Modify client-side schemas, database tables, and validation types to handle task `id` as a string instead of an integer.
- [ ] **Rename Fields**: Audit codebases and replace all property lookups and writes for `.done` with `.completed`.
- [ ] **Add `project_id`**: Update all task instantiation/creation payloads to include the required `project_id` property.
- [ ] **Adjust List Parsing**: Update response-parsing libraries to retrieve task lists from the response object's `items` attribute rather than the root array.
- [ ] **Implement Pagination**: Implement cursor pagination parsing utilizing the `next_cursor` property and the `?cursor=` query parameter to iterate over full sets.
- [ ] **Verify Integrations**: Run automated tests and perform validation checks on your application workflows.

---

## Upgrade Command

To upgrade the Zrb CLI to the latest v2 release, run:

```bash
pip install --upgrade zrb
```
