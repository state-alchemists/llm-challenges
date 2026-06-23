# Zrb Task API v2 Migration Guide

This guide assists developers in migrating their applications and integrations from Zrb Task API v1 to v2. 

v2 introduces support for projects, improved cursor-based pagination, and stricter authentication mechanisms. These enhancements result in several breaking changes that you must address before upgrading.

---

## Table of Contents
1. [Endpoint URL Prefixing](#1-endpoint-url-prefixing)
2. [Authentication Header](#2-authentication-header)
3. [Task ID Type Change](#3-task-id-type-change)
4. [Task Field Renamed (`done` to `completed`)](#4-task-field-renamed-done-to-completed)
5. [Required `project_id` for Task Creation](#5-required-project_id-for-task-creation)
6. [Paginated List Envelope](#6-paginated-list-envelope)
7. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
8. [Upgrading the CLI](#upgrading-the-cli)

---

## Breaking Changes

### 1. Endpoint URL Prefixing
All API endpoints are now isolated under a `/v2/` path prefix to allow side-by-side versioning and ensure zero disruption to legacy integrations still running on v1.

#### Before (v1)
```http
GET /tasks
GET /tasks/42
POST /tasks
```

#### After (v2)
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
```

---

### 2. Authentication Header
To align with security best practices, the custom `X-Auth-Token` header has been deprecated and replaced with standard Bearer Token authentication. Legacy headers will result in `HTTP 401 Unauthorized`.

#### Before (v1)
```http
GET /tasks HTTP/1.1
X-Auth-Token: your_api_key_here
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer your_api_token_here
```

---

### 3. Task ID Type Change
To support distributed generation of identifiers and avoid ID exhaustion, task `id`s have transitioned from sequential integers to globally unique UUIDv4 strings.

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

### 4. Task Field Renamed (`done` to `completed`)
The `done` boolean field on the task model has been renamed to `completed` for grammatical consistency across task tracking and project management resources.

#### Before (v1)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required `project_id` for Task Creation
With the introduction of Multi-Project support in v2, tasks can no longer exist in isolation. Every task must belong to a project. The `project_id` field is now mandatory on task creation; omitting it returns `HTTP 422 Unprocessable Entity`.

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

### 6. Paginated List Envelope
To prevent memory issues and improve load times, list queries no longer return bare JSON arrays. They now return a structured, cursor-paginated envelope containing paging metadata.

#### Before (v1)
```json
// GET /tasks
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

#### After (v2)
```json
// GET /v2/tasks
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "..."
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
*Note: Pass `?cursor=<next_cursor>` to request subsequent pages.*

---

## Step-by-Step Migration Checklist

Follow these steps to transition your client applications smoothly:

- [ ] **Step 1: Update API Base Paths**
  Prepend `/v2` to all task-related URL routes in your client code or configuration.
- [ ] **Step 2: Update Authentication Headers**
  Replace `X-Auth-Token: <key>` with standard HTTP `Authorization: Bearer <token>` across all API client initializations.
- [ ] **Step 3: Update Datastore Schemas & ID Parsers**
  Ensure any local databases, state management stores, or parsing logic expecting task IDs as integers are refactored to support UUID strings.
- [ ] **Step 4: Update Object Field References**
  Refactor frontend templates, state variables, and parsers to use the renamed `completed` boolean property instead of the legacy `done` property.
- [ ] **Step 5: Incorporate Project IDs on Creation**
  Modify your task creation forms or background jobs to fetch/supply a valid `project_id` when invoking `POST /v2/tasks`.
- [ ] **Step 6: Refactor Collection List Handling**
  Rewrite collection parsing logic from handling direct arrays to unwrapping the paginated object envelope (`response.items`). Integrate cursor-based loop handling if fetching multiple pages.
- [ ] **Step 7: Verify against the v2 Spec**
  Run integration tests against the new `/v2` endpoints to confirm request validation, header formatting, and object structures conform to the v2 specifications.

---

## Upgrading the CLI

To upgrade your local Zrb installation to the latest v2 release, run the appropriate command for your environment:

### Using pip (Python Package Installer)
```bash
pip install --upgrade zrb
```

### Using pipx (Recommended for global CLIs)
```bash
pipx upgrade zrb
```
