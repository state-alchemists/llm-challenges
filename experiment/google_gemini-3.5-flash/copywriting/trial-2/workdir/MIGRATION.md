# Zrb CLI v2 Migration Guide

Zrb CLI v2 introduces several powerful new capabilities including project namespaces, robust cursor-based pagination, and stricter authentication. 

To support these features, this release contains several breaking API and schema changes. This guide provides a detailed overview of these breaking changes, before-and-after examples, and an actionable checklist to help you migrate your integration from v1 to v2 smoothly.

---

## Breaking Changes Summary

1. [Endpoint Prefix Change (`/v2/`)](#1-endpoint-prefix-change-v2)
2. [Authentication Header Change (`Authorization: Bearer`)](#2-authentication-header-change-authorization-bearer)
3. [Task Identifier Type Change (Integer to UUID)](#3-task-identifier-type-change-integer-to-uuid)
4. [Renamed Completion Field (`done` to `completed`)](#4-renamed-completion-field-done-to-completed)
5. [Mandatory Project Association (`project_id`)](#5-mandatory-project-association-project_id)
6. [Paginated List Envelope Response (No More Bare Arrays)](#6-paginated-list-envelope-response-no-more-bare-arrays)

---

## Breaking Changes Details

### 1. Endpoint Prefix Change (`/v2/`)

All API routes have been moved under the `/v2/` namespace to allow for concurrent versioning and side-by-side deployment of the newer API.

#### Before (v1)
Clients made requests directly to `/tasks`:
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

### 2. Authentication Header Change (`Authorization: Bearer`)

The custom header `X-Auth-Token` has been deprecated and replaced with standard `Authorization: Bearer` tokens. Requests that attempt to use `X-Auth-Token` in v2 will be rejected with an `HTTP 401 Unauthorized` status.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: zrb_api_key_v1_example
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer zrb_api_token_v2_example
```

---

### 3. Task Identifier Type Change (Integer to UUID)

To prevent ID conflicts across projects and distributed clients, task identifiers have transitioned from auto-assigned integers to globally unique UUID strings.

#### Before (v1) Task Schema
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2) Task Schema
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

### 4. Renamed Completion Field (`done` to `completed`)

The `done` boolean field on the Task object has been renamed to `completed` to maintain consistency with industry standard naming conventions.

#### Before (v1)
Task representation or payload:
```json
{
  "title": "Update documentation",
  "done": true
}
```

#### After (v2)
Task representation or payload:
```json
{
  "title": "Update documentation",
  "completed": true
}
```

---

### 5. Mandatory Project Association (`project_id`)

All tasks in v2 must belong to a project. The `project_id` string field is now a required parameter when creating tasks (`POST /v2/tasks`). Omitting this parameter from the payload will result in an `HTTP 422 Unprocessable Entity` error.

#### Before (v1) Task Creation Payload
```json
{
  "title": "New task title"
}
```

#### After (v2) Task Creation Payload
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Envelope Response (No More Bare Arrays)

In v1, retrieving the task list returned a bare JSON array. In v2, `GET /v2/tasks` returns a paginated JSON envelope to handle larger datasets efficiently. The list endpoint also supports the optional query parameters `cursor` and `limit` (which defaults to 20).

#### Before (v1) Response
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
    "created_at": "2024-01-15T11:00:00Z"
  }
]
```

#### After (v2) Response
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
      "id": "e5f67890-abcd-ef12-3456-7890a1b2c3d4",
      "title": "Ship v1",
      "completed": true,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T11:00:00Z"
    }
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Step-by-Step Migration Checklist

Follow this checklist to systematically upgrade your integration to v2:

- [ ] **Prefix Routes:** Update all HTTP client configurations or SDK calls to prepend `/v2` to task resource endpoints.
- [ ] **Update Auth Headers:** Change authorization headers from `X-Auth-Token: <token>` to standard `Authorization: Bearer <token>`.
- [ ] **Refactor ID Data Types:** Adjust your database schemas, downstream models, or internal serializers to accept UUID strings instead of auto-incrementing integers for the task `id`.
- [ ] **Rename State Fields:** Search and replace usages of the `done` boolean field on task objects with `completed` in your codebase and frontends.
- [ ] **Enforce `project_id`:** Modify your task creation client calls to provide a valid, non-empty `project_id` string parameter.
- [ ] **Update List Parsing:** Refactor lists-handling logic to parse the `items` array out of the new paginated envelope, and optionally implement cursor-based pagination utilizing the returned `next_cursor`.
- [ ] **Run Test Suite:** Execute your unit and integration test suites against a staging v2 backend to verify code compatibility.

---

## How to Upgrade

To upgrade your local CLI tool installation to the latest v2 version, run the following command:

### Standard Installation
```bash
pip install --upgrade zrb
```

### Pipx Installation (Recommended for CLI isolation)
```bash
pipx upgrade zrb
```
