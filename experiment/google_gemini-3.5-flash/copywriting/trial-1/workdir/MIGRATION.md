# Zrb Task API — v2 Migration Guide

This guide is designed to help developers transition their applications from Zrb Task API v1 to Zrb Task API v2. The v2 release introduces support for projects, improved pagination, and stricter, standard-compliant authentication.

---

## Overview of Breaking Changes

| # | Breaking Change | Impacted Component | Severity |
|---|---|---|---|
| 1 | [API Endpoint Version Prefix (`/v2/`)](#1-api-endpoint-version-prefix-v2) | Base URL & Routes | High |
| 2 | [Authentication Header Change](#2-authentication-header-change) | HTTP Header & Client Credentials | High |
| 3 | [Task ID Type Change (Integer ➔ UUID String)](#3-task-id-type-change-integer-➔-uuid-string) | Model schemas, DB Keys, Path Parameters | High |
| 4 | [Task Status Field Renamed (`done` ➔ `completed`)](#4-task-status-field-renamed-done-➔-completed) | Request & Response Schemas, Frontend | High |
| 5 | [Task Creation Requires `project_id`](#5-task-creation-requires-project_id) | Task Creation Payloads | High |
| 6 | [Paginated Envelope for List Endpoints](#6-paginated-envelope-for-list-endpoints) | List response parsing & Pagination loops | High |

---

## Detailed Breaking Changes & Code Examples

### 1. API Endpoint Version Prefix (`/v2/`)

All API routes in v2 are now namespace-prefixed with `/v2/` to support side-by-side versioning and future scalability.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.local
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.local
```

---

### 2. Authentication Header Change

The authentication mechanism has been updated to use the standard RFC-compliant HTTP `Authorization` Bearer token header instead of the legacy custom `X-Auth-Token` header.

*   Legacy `X-Auth-Token` headers will be rejected with an **HTTP 401 Unauthorized** error.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.local
X-Auth-Token: your_api_key_v1
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.local
Authorization: Bearer your_api_token_v2
```

---

### 3. Task ID Type Change (Integer ➔ UUID String)

To support decentralized task creation and prevent ID collisions across projects, the `id` field has been migrated from an auto-incrementing integer to a standard UUID string.

*   You must update internal data schemas, state management systems, and client-side routers that validate task IDs as integers.

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

### 4. Task Status Field Renamed (`done` ➔ `completed`)

The boolean field representing the completion status of a task has been renamed from `done` to `completed` for linguistic consistency and clarity.

*   Both the read payload (responses) and write payloads (for update/create) must use `completed`.

#### Before (v1 Update)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2 Update)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task Creation Requires `project_id`

Every task in v2 must be associated with a project. Consequently, the `project_id` parameter is now **required** when creating a task.

*   Omitting `project_id` in the `POST /v2/tasks` body will result in an **HTTP 422 Unprocessable Entity** validation error.

#### Before (v1 Create Payload)
```json
{
  "title": "New task title"
}
```

#### After (v2 Create Payload)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Envelope for List Endpoints

To manage response sizes and guarantee fast lookup times, list endpoints no longer return a bare array. They now return a structured pagination envelope containing `items`, `total`, and a `next_cursor` pointer.

*   Client logic iterating directly over the returned root array will throw parsing errors. Use cursor-based traversal with `?cursor=<next_cursor>` to fetch subsequent pages.

#### Before (v1 List Response)
```json
[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

#### After (v2 List Response)
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
  "total": 1,
  "next_cursor": "cursor_xyz"
}
```

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your implementation smoothly:

- [ ] **1. Upgrade SDKs/CLI:** Upgrade your local Zrb development environment to version 2.
- [ ] **2. Update API Base Paths:** Change the target base endpoints in your API configuration or client initialization code from `/` to `/v2/`.
- [ ] **3. Revise Authentication:** Replace `X-Auth-Token: <api_key>` headers with `Authorization: Bearer <api_token>` in all HTTP clients.
- [ ] **4. Update Schema ID Types:** Modify your application schemas, entity models, database tables, and local state management to handle Task `id` as a UUID string instead of an integer.
- [ ] **5. Map Fields (`done` ➔ `completed`):** Search your codebase for references to `.done` (or JSON key `"done"`) and update them to `.completed` (or JSON key `"completed"`).
- [ ] **6. Add `project_id` to Task Instantiation:** Update task creation forms, services, and script workflows to collect and send a valid `project_id` in the POST request body.
- [ ] **7. Adapt Array Iterators to Paginated Envelope:** Refactor list parsers (e.g., table components, lists) to unpack `.items` from the response body rather than treating the top-level response as an array. Implement `?cursor=` pagination logic using `.next_cursor`.
- [ ] **8. Run End-to-End Tests:** Verify system operations against the v2 dev/staging server to ensure there are no schema or authentication mismatches.

---

## Upgrade Command

To update your Zrb CLI and Python package to the latest v2 release, execute the following command:

```bash
pip install --upgrade zrb
```

*For globally installed environments using pipx, use:*

```bash
pipx upgrade zrb
```
