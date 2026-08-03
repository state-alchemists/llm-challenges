# Zrb Task API — v2 Migration Guide

This guide describes how to migrate your existing integrations from the Zrb Task API v1 to v2.

The v2 release introduces several breaking changes to support structured projects, robust pagination, and more secure authentication mechanisms.

---

## Table of Breaking Changes

| Breaking Change | Impact | References |
| --- | --- | --- |
| [1. Endpoint Path Prefixing](#1-endpoint-path-prefixing) | All URLs now require a `/v2/` prefix | `v1_spec.md:29-82`, `v2_spec.md:62-114` |
| [2. Authentication Header Change](#2-authentication-header-change) | Header updated from `X-Auth-Token` to standard `Authorization: Bearer` token | `v1_spec.md:3-9`, `v2_spec.md:18-26` |
| [3. Task ID Format Change](#3-task-id-format-change) | Task `id` is now a UUID string instead of an integer | `v1_spec.md:24`, `v2_spec.md:42` |
| [4. Completion Field Renamed](#4-completion-field-renamed) | Task field `done` is renamed to `completed` | `v1_spec.md:26`, `v2_spec.md:44` |
| [5. Task Creation Requires Project ID](#5-task-creation-requires-project-id) | A valid `project_id` string is now mandatory when creating a task | `v1_spec.md:51-62`, `v2_spec.md:80-92` |
| [6. List Endpoint Response Envelope](#6-list-endpoint-response-envelope) | List responses return a paginated object instead of a bare array | `v1_spec.md:31-43`, `v2_spec.md:48-60` |

---

## Detailed Breaking Changes and Code Examples

### 1. Endpoint Path Prefixing

All API endpoints are now nested under the `/v2/` path prefix. Requests directed to the old v1 root paths will fail with `404 Not Found` or route to deprecated v1 services.

#### Before (v1)
```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

#### After (v2)
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 2. Authentication Header Change

The custom authentication header `X-Auth-Token` has been deprecated in favor of the standard HTTP `Authorization` Bearer token scheme. Submitting requests using `X-Auth-Token` in v2 will result in an HTTP `401 Unauthorized` response.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: v1_token_secret_123
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer v2_token_secret_123
```

### 3. Task ID Format Change

To support distributed systems and prevent ID enumeration, Task IDs have transitioned from auto-incrementing integers to standard UUID strings. Client-side database schemas, memory-mapping structures, and routing parameters must be updated to support strings instead of numbers.

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

### 4. Completion Field Renamed

The task status boolean field `done` is now renamed to `completed`. This change applies to both the task payload schemas returned by the API and the write payloads submitted during task updates.

#### Before (v1)
*Response / Request Payload:*
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2)
*Response / Request Payload:*
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Task Creation Requires Project ID

With the introduction of structured projects, every task must be assigned to an active project. Creating a task (`POST /v2/tasks`) now requires passing a `project_id` field in the request body. Omitting this field results in an HTTP `422 Unprocessable Entity` response.

#### Before (v1)
```json
{
  "title": "New task title"
}
```

#### After (v2)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoint Response Envelope

In v1, calling `GET /tasks` returned a bare list/array containing task objects. In v2, `GET /v2/tasks` returns a paginated JSON object envelope containing `items`, `total`, and a `next_cursor` field. This facilitates cursor-based pagination. To fetch subsequent pages, append the returned cursor value to the request: `?cursor=<next_cursor>`.

#### Before (v1)
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

---

## Step-by-Step Migration Checklist

Follow this checklist to systematically migrate your v1 integrations to v2:

- [ ] **1. Schema Updates**:
  - Update local database tables or interface types: change task `id` from integer to UUID string.
  - Rename local model property/column from `done` to `completed`.
  - Add `project_id` string property to task models.
- [ ] **2. Auth Configuration**:
  - Swap HTTP client header from `X-Auth-Token: <token>` to `Authorization: Bearer <token>`.
- [ ] **3. Endpoint Routes**:
  - Prepend `/v2` to all existing Zrb task endpoint paths (e.g., path `/tasks` becomes `/v2/tasks`).
- [ ] **4. Task Creation Payload**:
  - Update all `POST` requests to include a valid `project_id` key and value.
- [ ] **5. Response Parsing Adjustment**:
  - Reconfigure collection endpoints (e.g., `GET /v2/tasks`) to extract the actual tasks list from the `.items` field of the returned envelope object rather than parsing a bare array directly.
- [ ] **6. Pagination Handling**:
  - Update page fetching routines to utilize cursor-based pagination using `next_cursor` and the `?cursor=` query parameter.
- [ ] **7. CLI Update**:
  - Run the CLI upgrade command to install the latest version of Zrb.

---

## Upgrade Command

To update your Zrb CLI installation to v2, run:

```bash
pip install --upgrade zrb
```
