# Zrb Task API — v2 Migration Guide

Welcome to the migration guide for the Zrb Task API v2. This release introduces native project scoping, robust cursor-based pagination, and standard token-based authentication to deliver a more secure, performant, and developer-friendly experience.

Several v1 fields, endpoints, and integration conventions have been modified. This document provides a detailed breakdown of these breaking changes along with before/after code examples to guide you through the transition.

---

## Table of Contents
- [Breaking Changes Summary](#breaking-changes-summary)
- [Detailed Breaking Changes](#detailed-breaking-changes)
  1. [Endpoint Path Prefixing (`/v2/`)](#1-endpoint-path-prefixing-v2)
  2. [Authentication Header (`Authorization: Bearer`)](#2-authentication-header-authorization-bearer)
  3. [Task ID Type Change (`integer` to `UUID string`)](#3-task-id-type-change-integer-to-uuid-string)
  4. [Task Status Field Rename (`done` to `completed`)](#4-task-status-field-rename-done-to-completed)
  5. [Required `project_id` Field on Task Creation](#5-required-project_id-field-on-task-creation)
  6. [Paginated List Response Envelope](#6-paginated-list-response-envelope)
- [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
- [Upgrade Command](#upgrade-command)

---

## Breaking Changes Summary

Review the summary table below for a high-level overview of the differences between v1 and v2.

| Feature | v1 (Deprecated) | v2 (Current) | Impact Severity |
| :--- | :--- | :--- | :--- |
| **API Path Prefix** | None (`/tasks`) | `/v2/` prefix (`/v2/tasks`) | **High** |
| **Authentication** | `X-Auth-Token` Header | `Authorization: Bearer` Header | **High** |
| **Task ID Type** | Auto-incremented `integer` | `UUID string` | **High** |
| **Status Field** | `done` (boolean) | `completed` (boolean) | **Medium** |
| **Task Creation** | Requiring only `title` | Requiring both `title` and `project_id` | **Medium** |
| **List Endpoints** | Bare JSON array (`[...]`) | Paginated envelope (`{"items": [...]}`) | **Medium** |

---

## Detailed Breaking Changes

### 1. Endpoint Path Prefixing (`/v2/`)

All API routes have been moved behind the `/v2/` prefix to allow version co-existence and seamless future upgrades.

#### Before (v1)
Endpoints are exposed directly under the root context:
```http
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

#### After (v2)
Endpoints must be requested via the `/v2/` path prefix:
```http
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication Header (`Authorization: Bearer`)

We have retired the proprietary `X-Auth-Token` header in favor of standard HTTP Bearer Token authentication. 

> ⚠️ **Warning**: Requests sending `X-Auth-Token` to v2 endpoints will be rejected with an **HTTP 401 Unauthorized** status code.

#### Before (v1)
```bash
curl -X GET http://api.zrb.local/tasks \
  -H "X-Auth-Token: your_api_token_here"
```

#### After (v2)
```bash
curl -X GET http://api.zrb.local/v2/tasks \
  -H "Authorization: Bearer your_api_token_here"
```

---

### 3. Task ID Type Change (`integer` to `UUID string`)

To prevent sequential ID enumeration and better support distributed task systems, Task IDs have been upgraded from simple integers to standard UUIDv4 strings.

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

### 4. Task Status Field Rename (`done` to `completed`)

The task state boolean field `done` has been renamed to `completed`. Update your data models, database columns, and frontend state properties accordingly.

#### Before (v1)
```bash
curl -X PUT http://api.zrb.local/tasks/42 \
  -H "X-Auth-Token: your_api_token_here" \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

#### After (v2)
```bash
curl -X PUT http://api.zrb.local/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer your_api_token_here" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

---

### 5. Required `project_id` Field on Task Creation

With the introduction of multi-project scoping, every task must reside within an existing project context. The `project_id` field is now mandatory.

> ⚠️ **Warning**: Submitting a `POST /v2/tasks` request without a `project_id` will return an **HTTP 422 Unprocessable Entity** error.

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

### 6. Paginated List Response Envelope

To optimize performance and bandwidth, list endpoints no longer return an unbounded, bare array of tasks. Instead, they return a standard paginated response envelope.

#### Query Parameters
- `limit` — Maximum results per page (optional, default: `20`).
- `cursor` — Pagination token (optional).

#### Before (v1)
`GET /tasks` returned a bare JSON array:
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

#### After (v2)
`GET /v2/tasks` returns a paginated JSON object:
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

To fetch subsequent pages, pass the `next_cursor` value into the `cursor` query parameter of your next request:
```bash
curl -X GET "http://api.zrb.local/v2/tasks?limit=10&cursor=cursor_xyz" \
  -H "Authorization: Bearer your_api_token_here"
```

---

## Step-by-Step Migration Checklist

Follow this systematic checklist to ensure a safe transition from v1 to v2:

- [ ] **1. Upgrade Zrb CLI & SDK dependencies**
  - Run the official upgrade command to fetch and install the latest v2 libraries.
- [ ] **2. Refactor Internal Schema and Data Models**
  - Convert database columns/schemas for task IDs from `integer` to `UUID string`.
  - Rename storage field `done` to `completed`.
  - Introduce the mandatory `project_id` foreign key/field to database schemas.
- [ ] **3. Update Client Authentication**
  - Replace the custom `X-Auth-Token` header with standard standard `Authorization: Bearer <token>` headers in all API callers.
- [ ] **4. Adapt API Endpoints and Path Resolvers**
  - Prefix all endpoint routes with `/v2/` (e.g. `GET /v2/tasks`).
  - Update any router parameters parsing ID from integer parsing to string/UUID format.
- [ ] **5. Update Request Payloads**
  - Inject the required `project_id` field in all task creation payloads (`POST /v2/tasks`).
  - Update task modifier endpoints (`PUT /v2/tasks/{id}`) to send `completed` instead of `done`.
- [ ] **6. Adjust Response Parsing**
  - Refactor all code consuming task list endpoints to read from the `.items` property of the response envelope instead of processing a bare array directly.
  - Implement loop/recursion mechanics for multi-page requests using `.next_cursor`.
- [ ] **7. Verify Changes**
  - Run existing test suites against the v2 endpoints.
  - Assert that appropriate HTTP 401 (auth failure), 422 (missing project context), and 404 (invalid UUID format or resource not found) errors are handled gracefully.

---

## Upgrade Command

To update your Zrb CLI and Python package dependencies to the latest v2 release, run:

```bash
pip install --upgrade zrb
```

*For global installations managed via `pipx`, run:*
```bash
pipx upgrade zrb
```
