# Zrb CLI v2 Migration Guide

This guide outlines the breaking changes introduced in Zrb CLI v2 and provides a step-by-step path for migrating your existing v1 integrations. 

Zrb v2 introduces a transition to structured projects, standardized UUID identifiers, robust cursor-based pagination, and industry-standard Bearer token authentication.

---

## Table of Contents
1. [Breaking Changes](#breaking-changes)
   - [1. Endpoint Path Prefix Changes](#1-endpoint-path-prefix-changes)
   - [2. Authentication Header Changes](#2-authentication-header-changes)
   - [3. Task ID Type Change (Integer to UUID)](#3-task-id-type-change-integer-to-uuid)
   - [4. Task Field Rename (`done` to `completed`)](#4-task-field-rename-done-to-completed)
   - [5. Task Creation Requires `project_id`](#5-task-creation-requires-project_id)
   - [6. Paginated Envelope on List Endpoints](#6-paginated-envelope-on-list-endpoints)
2. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
3. [Upgrading the CLI](#upgrading-the-cli)

---

## Breaking Changes

### 1. Endpoint Path Prefix Changes
All endpoints are now version-prefixed with `/v2/` to support side-by-side deployment of older clients while encouraging a clear upgrade path.

#### Before (v1)
Endpoints were exposed directly on the root path:
```http
GET /tasks
POST /tasks
GET /tasks/42
```

#### After (v2)
All endpoints must be requested under `/v2`:
```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header Changes
To adhere to standard security practices, the custom `X-Auth-Token` header has been replaced by Bearer token authentication. Requests utilizing the old header in v2 will be rejected with an `HTTP 401 Unauthorized` status.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key_here
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token_here
```

---

### 3. Task ID Type Change (Integer to UUID)
Task identifiers have been changed from auto-incrementing integers to globally unique UUID strings. This avoids ID enumeration and collision issues across distributed environments.

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

### 4. Task Field Rename (`done` to `completed`)
The `done` boolean field on the Task object has been renamed to `completed` to maintain grammatical consistency with project and status models.

#### Before (v1)
Request body for updating a task:
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2)
Request body for updating a task:
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task Creation Requires `project_id`
Tasks can no longer exist globally; they must be associated with a project. Consequently, the `project_id` string field is now mandatory during task creation. Omitting it will result in an `HTTP 422 Unprocessable Entity` error.

#### Before (v1)
```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

#### After (v2)
```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Envelope on List Endpoints
List endpoints no longer return a bare JSON array. To support scale and efficient querying, v2 endpoints return a paginated JSON envelope containing metadata and a cursor for fetching subsequent pages.

#### Before (v1)
Response from `GET /tasks`:
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
Response from `GET /v2/tasks`:
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
  "total": 2,
  "next_cursor": null
}
```

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your codebases and workflows from Zrb CLI v1 to v2:

- [ ] **1. Upgrade Zrb CLI**
  Upgrade your local CLI installation to the latest v2 release.
- [ ] **2. Update Authentication Settings**
  Locate where your API key is stored and configure your clients to send it as `Authorization: Bearer <token>` rather than `X-Auth-Token: <token>`.
- [ ] **3. Prepend Base Endpoint Paths**
  Update your API base path configurations or route paths to prepend `/v2` to all `tasks` endpoints.
- [ ] **4. Refactor ID Parsing & Storage Types**
  Locate any database schemas, structures, or state-management code casting Task `id`s to integers, and convert them to handle UUID strings.
- [ ] **5. Rename Task Status Fields**
  Perform a search and replace in your client codebase to rename the `done` attribute to `completed`.
- [ ] **6. Provide a `project_id` on Task Creation**
  Modify your task creation payload to retrieve and send a valid `project_id`.
- [ ] **7. Refactor List Endpoint Parsers**
  Update response parsers for listing tasks to read from the `.items` array of the returned JSON envelope instead of treating the root response as an array. Implement support for `?cursor=` parameters for fetching next pages if processing large volumes of tasks.
- [ ] **8. Run & Verify Local Integration Tests**
  Run your test suite targeting a v2 endpoint mock or staging environment to ensure all HTTP response codes (e.g., HTTP 200, 201, 204, 401, and 422) are correctly handled.

---

## Upgrading the CLI

To upgrade your Zrb CLI installation to v2, run the following command depending on your environment:

### Using pip
```bash
pip install --upgrade zrb
```

### Using pipx (Recommended)
```bash
pipx upgrade zrb
```
