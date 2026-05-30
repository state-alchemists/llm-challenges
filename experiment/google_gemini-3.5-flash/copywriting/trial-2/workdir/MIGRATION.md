# Zrb CLI v2 Migration Guide

Zrb v2 introduces support for project-based task organization, standard bearer-token authentication, robust cursor pagination, and standardized UUID identifiers. While these changes make the platform more secure and scalable, they introduce breaking changes for integrations built against Zrb v1.

This guide provides a comprehensive breakdown of all breaking changes, before/after code and API examples, a step-by-step migration checklist, and CLI upgrade instructions.

---

## Table of Contents
- [Breaking Changes Summary](#breaking-changes-summary)
- [Detailed Breaking Changes](#detailed-breaking-changes)
  1. [API Endpoint Path Prefixing](#1-api-endpoint-path-prefixing)
  2. [Authentication Header Protocol](#2-authentication-header-protocol)
  3. [Task Identifier Type Change](#3-task-identifier-type-change)
  4. [Field Rename: `done` to `completed`](#4-field-rename-done-to-completed)
  5. [Mandatory Task Project Association](#5-mandatory-task-project-association)
  6. [Response Schema for Lists (Paginated Envelope)](#6-response-schema-for-lists-paginated-envelope)
- [Migration Checklist](#migration-checklist)
- [Upgrading the CLI](#upgrading-the-cli)

---

## Breaking Changes Summary

| Breaking Change | v1 API Behavior | v2 API Behavior | Impact |
| :--- | :--- | :--- | :--- |
| **Endpoint Prefix** | Root path (e.g. `/tasks`) | Prefixed with `/v2/` (e.g. `/v2/tasks`) | Immediate 404 for old routes |
| **Authentication** | `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` | Immediate 401 Unauthorized |
| **Task ID Type** | Auto-assigned sequential integer | RFC 4122 UUID string | Parsing/Type matching errors |
| **Task Done Field** | Boolean field `done` | Boolean field `completed` | Serialization and rendering errors |
| **Task Creation** | Title only | Requires `project_id` | Immediate 422 Unprocessable Entity |
| **List Responses** | Bare JSON array | Paginated envelope (`items`, `total`, etc.) | Client-side response parsing failures |

---

## Detailed Breaking Changes

### 1. API Endpoint Path Prefixing

To support versioned routing and preserve future API evolution, all API endpoints are now namespace-isolated under a `/v2/` prefix.

#### Before (v1)
Endpoints were accessed at the root path:
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
```

#### After (v2)
All requests must be prefixed with `/v2/`:
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
```

---

### 2. Authentication Header Protocol

Zrb has migrated to the industry-standard Bearer Token authentication schema. The custom `X-Auth-Token` header is deprecated, and its usage in v2 will result in `HTTP 401 Unauthorized`.

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

### 3. Task Identifier Type Change

Task identifiers (`id`) have been migrated from incremental integers to globally unique UUID strings. This avoids primary key enumeration risks and supports multi-region write synchronization. Any frontend, client, or database schema that strictly expects an integer task ID will fail.

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

### 4. Field Rename: `done` to `completed`

The `done` boolean field on the task object has been renamed to `completed` for consistency across Zrb's ecosystem. This change affects list responses, single resource responses, and task update payloads.

#### Before (v1 Update)
```http
PUT /tasks/42 HTTP/1.1
Host: api.zrb.dev
Content-Type: application/json

{
  "done": true
}
```

#### After (v2 Update)
```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Host: api.zrb.dev
Content-Type: application/json

{
  "completed": true
}
```

---

### 5. Mandatory Task Project Association

In v2, all tasks must belong to a parent project. The `project_id` field is now a **required** attribute when creating a task. Omitting `project_id` in a `POST` request will return a validation error (`HTTP 422 Unprocessable Entity`).

#### Before (v1 Create)
```http
POST /tasks HTTP/1.1
Host: api.zrb.dev
Content-Type: application/json

{
  "title": "New task title"
}
```

#### After (v2 Create)
```http
POST /v2/tasks HTTP/1.1
Host: api.zrb.dev
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Response Schema for Lists (Paginated Envelope)

To scale task listings and prevent out-of-memory errors on large collections, v2 replaces bare-array list responses with a structured paginated envelope. The envelope returns task items alongside pagination indicators (`total`, `next_cursor`).

To traverse pages, fetch the initial page, retrieve `next_cursor`, and supply it as a query parameter in subsequent requests (e.g. `?cursor=<cursor_hash>&limit=20`).

#### Before (v1 List Response)
```http
HTTP/1.1 200 OK
Content-Type: application/json

[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:00:00Z"
  },
  {
    "id": 2,
    "title": "Ship v1",
    "done": true,
    "created_at": "2024-01-15T10:15:00Z"
  }
]
```

#### After (v2 List Response)
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:00:00Z"
    },
    {
      "id": "f8e7d6c5-b4a3-2109-8765-43210fedcba9",
      "title": "Ship v1",
      "completed": true,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:15:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

Follow these steps to upgrade your application integration smoothly from v1 to v2:

- [ ] **Upgrade the Zrb CLI**
  Ensure your CLI tool is upgraded to version 2 (see instructions below).
- [ ] **Update Authentication Credentials & Headers**
  Configure your client headers to use the standard Bearer scheme:
  - Locate all occurrences of the `X-Auth-Token` header.
  - Replace them with `Authorization: Bearer <token>`.
- [ ] **Refactor Base URLs**
  - Prefix your client base URLs or paths with `/v2/` (e.g. pointing `/tasks` clients to `/v2/tasks`).
- [ ] **Update Client Data Schemas**
  - Update ID parsers to handle 36-character UUID strings instead of sequential integers.
  - Rename the `done` boolean field to `completed` in your models, serialization, and presentation layers.
- [ ] **Modify Task Creation Payloads**
  - Identify a default or explicit `project_id` (e.g. `proj_abc123`).
  - Add the `project_id` field as a mandatory property to all `POST` task requests.
- [ ] **Rewrite List Parsing Logics**
  - Change response processors that parse list endpoints.
  - Extract the items list from the `.items` array instead of parsing the root response as an array.
  - (Optional) Implement cursor pagination using `.next_cursor` for large list iterations.
- [ ] **Verify & Test End-to-End**
  - Run regression tests on creation, reading, updating, deleting, and paginated listing of tasks.

---

## Upgrading the CLI

To get the latest version of the Zrb CLI, run the following upgrade command:

```bash
pip install --upgrade zrb
```

If you are using `pipx`, you can run:

```bash
pipx upgrade zrb
```
