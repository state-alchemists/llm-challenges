# Zrb Task API — v1 to v2 Migration Guide

This guide describes how to migrate your client applications and integrations from the Zrb Task API v1 to the new v2 API. 

The v2 release introduces first-class projects, cursor-based pagination, enhanced security, and stricter schema validation. Several of these enhancements introduce breaking changes that require updates to your codebase.

---

## Table of Contents

- [Summary of Breaking Changes](#summary-of-breaking-changes)
- [Breaking Changes Deep Dive](#breaking-changes-deep-dive)
  1. [All Endpoint Paths Prefixed with `/v2/`](#1-all-endpoint-paths-prefixed-with-v2)
  2. [Authentication Header Standardized to Bearer Token](#2-authentication-header-standardized-to-bearer-token)
  3. [Task ID Type Migrated to UUID String](#3-task-id-type-migrated-to-uuid-string)
  4. [Task Status Field Renamed `done` to `completed`](#4-task-status-field-renamed-done-to-completed)
  5. [Mandatory `project_id` Field on Task Creation](#5-mandatory-project_id-field-on-task-creation)
  6. [Paginated Envelope Response for List Endpoints](#6-paginated-envelope-response-for-list-endpoints)
- [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
- [Upgrading the CLI](#upgrading-the-cli)

---

## Summary of Breaking Changes

The following table summarizes the key changes from v1 to v2:

| Feature / Behavior | v1 (Deprecated) | v2 (Current) | Impact |
| :--- | :--- | :--- | :--- |
| **Endpoint Prefix** | `/tasks` | `/v2/tasks` | High |
| **Auth Header** | `X-Auth-Token: <key>` | `Authorization: Bearer <token>` | High |
| **Task ID Format** | Integer (e.g., `42`) | UUID String (e.g., `"a1b2..."`) | High |
| **Status Boolean** | `done` | `completed` | Medium |
| **Required Create Fields** | `title` | `title`, `project_id` | High |
| **List Response Format** | Bare JSON array (`[...]`) | Paginated JSON envelope (`{"items": ...}`) | High |

---

## Breaking Changes Deep Dive

### 1. All Endpoint Paths Prefixed with `/v2/`

To support parallel API versioning, all resource endpoints are now namespaced under the `/v2/` prefix.

#### Before (v1)
Clients sent requests directly to the base `/tasks` namespace:

```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

#### After (v2)
All requests must target the `/v2/tasks` namespace:

```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

*Note: Accessing v1 paths on the v2 server will result in `404 Not Found` errors unless your routing infrastructure supports legacy fallbacks.*

---

### 2. Authentication Header Standardized to Bearer Token

The custom `X-Auth-Token` header has been deprecated in favor of the industry-standard `Authorization: Bearer` schema.

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

*Warning: Requests sending the legacy `X-Auth-Token` header to v2 endpoints will be rejected with an `HTTP 401 Unauthorized` status.*

---

### 3. Task ID Type Migrated to UUID String

To prepare for distributed architecture and offline-first clients, task IDs are now standard UUID strings instead of auto-incrementing integers.

#### Before (v1)
The ID was returned and referenced as an integer:

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2)
The ID is returned and referenced as a 36-character UUID string:

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

*Note: Update your data-type parsers, client-side model structures, and database foreign keys to support 36-character string identifiers.*

---

### 4. Task Status Field Renamed `done` to `completed`

The boolean state flag indicating task completion has been renamed from `done` to `completed` to maintain consistency with our domain vocabulary.

#### Before (v1)
The task payload utilized the `done` field:

```json
{
  "title": "Update documentation",
  "done": true
}
```

#### After (v2)
The task payload now utilizes the `completed` field:

```json
{
  "title": "Update documentation",
  "completed": true
}
```

*Note: If you use the old `done` key in a `PUT /v2/tasks/{id}` request, it will be ignored, and the task status will not update.*

---

### 5. Mandatory `project_id` Field on Task Creation

With the introduction of Projects in v2, tasks cannot exist in isolation. Every task must belong to a project.

#### Before (v1)
Creating a task only required a `title`:

```json
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "Write tests"
}
```

#### After (v2)
Creating a task requires both a `title` and a valid `project_id` identifier:

```json
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "Write tests",
  "project_id": "proj_abc123"
}
```

*Warning: Omitting `project_id` from a `POST /v2/tasks` request body will result in an `HTTP 422 Unprocessable Entity` response.*

---

### 6. Paginated Envelope Response for List Endpoints

To prevent performance degradation on large datasets, the list tasks endpoint no longer returns a bare JSON array. It now returns a paginated JSON envelope.

#### Before (v1)
`GET /tasks` returned a bare JSON array containing all matching tasks:

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
`GET /v2/tasks` returns an object envelope containing paginated metadata along with the array of tasks in the `items` field:

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

To fetch subsequent pages, pass the returned `next_cursor` as a query parameter:

```http
GET /v2/tasks?cursor=cursor_xyz&limit=20 HTTP/1.1
Authorization: Bearer your_api_token_v2
```

---

## Step-by-Step Migration Checklist

Follow these steps to safely transition your application from v1 to v2:

- [ ] **1. Review Dependencies & Data Models**
  - Update your local task data models to accept `id` as a UUID string rather than an integer.
  - Rename the `done` boolean field to `completed` in your client-side schemas, validation models, and persistence layer.
  - Add a `project_id` string field to your local task models.

- [ ] **2. Update Authentication Logic**
  - Replace instances of the `X-Auth-Token` header with the standard `Authorization` header.
  - Ensure the key/token value is formatted with the `Bearer ` prefix.

- [ ] **3. Update URL Routes**
  - Prepend all API task routes with the `/v2/` prefix.

- [ ] **4. Modify Task Creation Logic**
  - Audit all code paths where tasks are created (`POST` requests) and ensure a valid `project_id` is supplied in the request body.

- [ ] **5. Refactor List Integration & Pagination**
  - Refactor handlers for `GET /tasks` to expect the paginated JSON envelope (`items`, `total`, `next_cursor`) rather than a bare array.
  - Update UI and paging controls to utilize the cursor-based `cursor` query parameter and optional `limit` parameter instead of offset-based pagination.

- [ ] **6. Audit Task Update Operations**
  - Verify that updates (`PUT` requests) reference UUID strings in their URI paths and use the `completed` field instead of `done` in request bodies.

- [ ] **7. Run and Verify Test Suites**
  - Ensure all request parsers handle HTTP 401 (unauthorized) and HTTP 422 (unprocessable entity) gracefully.
  - Confirm all integration tests pass against the new endpoints.

---

## Upgrading the CLI

To upgrade your local CLI tool and use the latest v2 capabilities, run the following command in your terminal:

```bash
pip install --upgrade zrb
```
