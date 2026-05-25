# Zrb Task API — v1 to v2 Migration Guide

Welcome to the Zrb Task API v2 migration guide. Zrb v2 introduces several major architectural improvements, including structured projects, robust cursor-based pagination, UUIDs for stronger database integrity, and standard Bearer Token authentication. 

This document details every breaking change between v1 and v2 and provides explicit instructions and code examples to assist with your upgrade.

---

## Table of Contents
1. [Global Endpoint Prefixing (`/v2/`)](#1-global-endpoint-prefixing-v2)
2. [Authentication Protocol Migration (`X-Auth-Token` to `Bearer`)](#2-authentication-protocol-migration-x-auth-token-to-bearer)
3. [Task ID Format Change (Integer to UUID)](#3-task-id-format-change-integer-to-uuid)
4. [Field Renaming (`done` to `completed`)](#4-field-renaming-done-to-completed)
5. [Mandatory Project Association (`project_id`)](#5-mandatory-project-association-project_id)
6. [Paginated List Responses (Bare Array to Envelope)](#6-paginated-list-responses-bare-array-to-envelope)
7. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
8. [Upgrade Command](#upgrade-command)

---

## 1. Global Endpoint Prefixing (`/v2/`)

All resource endpoints in the Zrb Task API have been updated to use the `/v2/` version prefix to isolate v2 routing logic. Calling v1 endpoints without this prefix will result in a `404 Not Found` or standard routing failure.

### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
```

### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
```

---

## 2. Authentication Protocol Migration (`X-Auth-Token` to `Bearer`)

The legacy custom token header `X-Auth-Token` has been deprecated in favor of the standard HTTP `Authorization` header utilizing the `Bearer` scheme.

- **v1**: `X-Auth-Token: <your_api_key>`
- **v2**: `Authorization: Bearer <your_api_token>`

Any requests to v2 endpoints utilizing the old header style will be rejected with an `HTTP 401 Unauthorized` response.

### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: my-secret-api-key-123
```

### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer my-secret-api-key-123
```

---

## 3. Task ID Format Change (Integer to UUID)

To ensure global uniqueness across multiple distributed systems and to prevent sequential ID guessing (enumeration attacks), Task IDs have been changed from auto-incrementing integers to standard UUID strings.

- **v1**: `id` was an `integer` (e.g., `42`)
- **v2**: `id` is a `UUID` string (e.g., `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`)

If your database models, API client models, or client-side storage structures parse or validate Task IDs as integers, you must update them to support UUID strings.

### Before (v1 Task Object)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2 Task Object)
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

## 4. Field Renaming (`done` to `completed`)

To align with modern industry standards and to clarify the boolean nature of task status, the task field `done` has been renamed to `completed`.

- **v1**: Field named `done`
- **v2**: Field named `completed`

This affects update (`PUT`) payloads, creation overrides, and all JSON response payloads.

### Before (v1 Update Request)
```http
PUT /tasks/42 HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: my-secret-api-key-123
Content-Type: application/json

{
  "title": "Updated title",
  "done": true
}
```

### After (v2 Update Request)
```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer my-secret-api-key-123
Content-Type: application/json

{
  "title": "Updated title",
  "completed": true
}
```

---

## 5. Mandatory Project Association (`project_id`)

In v1, tasks were completely independent and lacked project-level scope. In v2, the Zrb Task API introduces a structured multi-project system. Accordingly, task creation (`POST /v2/tasks`) now requires a valid `project_id` identifier. 

Omitting `project_id` from the request payload will result in an `HTTP 422 Unprocessable Entity` validation error.

### Before (v1 Create Request)
```http
POST /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: my-secret-api-key-123
Content-Type: application/json

{
  "title": "New task title"
}
```

### After (v2 Create Request)
```http
POST /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer my-secret-api-key-123
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

## 6. Paginated List Responses (Bare Array to Envelope)

To improve system performance and memory utilization under heavy task loads, list endpoints no longer return a bare JSON array. Instead, they return a structured paginated envelope containing pagination metadata and an `items` array.

- **v1**: List endpoint returned a bare array `[...]`
- **v2**: List endpoint returns `{"items": [...], "total": 42, "next_cursor": "cursor_xyz"}`

To paginate through long lists, retrieve the `next_cursor` from the response envelope and pass it as a `cursor` query parameter on your next request (e.g., `/v2/tasks?cursor=cursor_xyz`). You may also customize page sizes using the `limit` query parameter (default is 20).

### Before (v1 List Response)
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2 List Response)
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
  "next_cursor": null
}
```

---

## Step-by-Step Migration Checklist

Follow this systematic checklist to migrate your client applications from v1 to v2:

- [ ] **Audit Request URLs**: Locate and update all API base and endpoint URL strings to include the `/v2/` path prefix.
- [ ] **Update Auth Headers**: Replace the custom `X-Auth-Token` header with the standard `Authorization: Bearer <token>` format across your HTTP client instances.
- [ ] **Adjust Task ID Types**: Modify database tables, local serialization models, and variable types to treat task `id` values as strings/UUIDs instead of integers.
- [ ] **Rename done to completed**: Update JSON serializing and deserializing mappings, model fields, and logic checks from `done` to `completed`.
- [ ] **Inject project_id on Creation**: Ensure your application retrieves a valid project identifier and supplies it as `project_id` in all task creation (`POST /v2/tasks`) payloads.
- [ ] **Adapt to List Envelopes**: Modify list parsing logic. Instead of handling a direct array response from `GET /v2/tasks`, extract target items from the `items` key of the returned dictionary, and implement cursor-based pagination loop using `next_cursor` when retrieving multiple pages of tasks.
- [ ] **Verify and Run Tests**: Run your suite of integration and regression tests against the updated v2 endpoints to ensure complete compliance.

---

## Upgrade Command

To upgrade your local CLI tool and client libraries to the v2 release of Zrb, execute:

```bash
pip install --upgrade zrb
```
