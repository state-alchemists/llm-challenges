# Zrb Task API — v1 to v2 Migration Guide

This guide describes the breaking changes introduced in the Zrb Task API v2 and provides the necessary steps and code examples to migrate your existing v1 integrations to v2.

## Table of Contents
1. [Base URL & Endpoint Prefix Changes](#1-base-url--endpoint-prefix-changes)
2. [Authentication Changes](#2-authentication-changes)
3. [Task Schema & Field Changes](#3-task-schema--field-changes)
4. [Task Creation Requirements](#4-task-creation-requirements)
5. [List Endpoint Pagination & Envelope Changes](#5-list-endpoint-pagination--envelope-changes)
6. [Step-by-Step Migration Checklist](#6-step-by-step-migration-checklist)
7. [Upgrading the CLI](#7-upgrading-the-cli)

---

## 1. Base URL & Endpoint Prefix Changes

To allow coexistence and safe versioning, all API endpoints are now prefixed with `/v2/`.

### Mapping of Endpoints

| Operation | v1 Endpoint | v2 Endpoint |
| :--- | :--- | :--- |
| **List Tasks** | `GET /tasks` | `GET /v2/tasks` |
| **Get Task** | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| **Create Task** | `POST /tasks` | `POST /v2/tasks` |
| **Update Task** | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| **Delete Task** | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

### Code Example

#### Before (v1)
```http
GET /tasks
```

#### After (v2)
```http
GET /v2/tasks
```

---

## 2. Authentication Changes

The authentication scheme has been updated from a custom header to a standard Bearer token scheme.

- **v1 Header**: `X-Auth-Token: <your_api_key>`
- **v2 Header**: `Authorization: Bearer <your_api_token>`

> ⚠️ **Warning**: Requests made to v2 endpoints using the legacy `X-Auth-Token` header will receive an **HTTP 401 Unauthorized** response.

### Code Example

#### Before (v1)
```http
GET /tasks
X-Auth-Token: task_api_key_123456
```

#### After (v2)
```http
GET /v2/tasks
Authorization: Bearer task_api_token_123456
```

---

## 3. Task Schema & Field Changes

The data model for a Task has been modified to support projects, UUIDs, and more descriptive naming.

### Key Changes
1. **`id` Field Type**: Changed from an **integer** (auto-assigned) to a **UUID string**.
2. **`done` Field Renamed**: Renamed to `completed` (boolean).
3. **`project_id` Field Added**: A new required string field associating the task with a project.

### Code Example

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

## 4. Task Creation Requirements

Creating a task now requires specifying the associated `project_id`.

- **v1 POST**: Required only a `title`.
- **v2 POST**: Requires both `title` and `project_id`.

> ⚠️ **Warning**: Omitting `project_id` in a v2 POST request will result in an **HTTP 422 Unprocessable Entity** response.

### Code Example

#### Before (v1 Create Request)
```http
POST /tasks
X-Auth-Token: task_api_key_123456
Content-Type: application/json

{
  "title": "New task title"
}
```

#### After (v2 Create Request)
```http
POST /v2/tasks
Authorization: Bearer task_api_token_123456
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

## 5. List Endpoint Pagination & Envelope Changes

In v1, calling the List Tasks endpoint returned a bare JSON array. In v2, to support scale and cursored pagination, the endpoint returns a structured envelope object containing pagination metadata.

### Envelope Structure
- **`items`**: Array of Task objects.
- **`total`**: Total number of tasks matching the query.
- **`next_cursor`**: A cursor string to fetch the next page.

### Query Parameters
- **`cursor`**: Optional. Pass the `next_cursor` value from the previous response to retrieve the next page of results.
- **`limit`**: Optional. Defines the maximum number of items per page (defaults to `20`).

### Code Example

#### Before (v1 List Response)
```http
HTTP/1.1 200 OK
Content-Type: application/json

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
    "created_at": "2024-01-15T11:00:00Z"
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
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## 6. Step-by-Step Migration Checklist

Follow these steps to migrate your codebase to v2:

- [ ] **Update Endpoint Prefixes**: Append `/v2` to all base API paths (e.g., from `/tasks` to `/v2/tasks`).
- [ ] **Refactor Authentication Headers**: Replace `X-Auth-Token: <token>` with `Authorization: Bearer <token>` in your HTTP client configuration.
- [ ] **Modify ID Handling**: Update database schemas, type annotations, and validation layers to handle `id` as a UUID string rather than an integer.
- [ ] **Rename Status Field**: Rename the `done` field to `completed` in your code models, payload serializers, and view templates.
- [ ] **Provide Project Context**: Update your task creation logic to supply a required `project_id` string when issuing `POST` requests.
- [ ] **Handle Paginated Envelopes**: Update your List response parsing to read from the `.items` property instead of expecting a bare root-level array.
- [ ] **Implement cursored pagination** (if fetching multiple pages) using the `next_cursor` and `cursor` query parameter.

---

## 7. Upgrading the CLI

To upgrade your local Zrb installation to the latest v2 release, run the following command based on your installation method:

### Using pipx (Recommended)
```bash
pipx upgrade zrb
```

### Using pip
```bash
pip install --upgrade zrb
```
