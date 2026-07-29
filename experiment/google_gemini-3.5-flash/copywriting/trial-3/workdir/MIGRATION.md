# Zrb Task API — v2 Migration Guide

Welcome to the Zrb Task API v2 migration guide. This document is designed to help developers currently using Zrb Task API v1 upgrade their applications to v2. 

v2 introduces support for projects, improved cursor-based pagination, and stricter, standardized authentication. This release contains several breaking changes that will require modifications to your codebase.

---

## Table of Contents

- [Breaking Changes Summary](#breaking-changes-summary)
- [Breaking Changes & Examples](#breaking-changes--examples)
  1. [Base URL Endpoint Prefix `/v2/`](#1-base-url-endpoint-prefix-v2)
  2. [Authentication Header (`X-Auth-Token` to `Bearer` Token)](#2-authentication-header-x-auth-token-to-bearer-token)
  3. [Task `id` Type (Integer to UUID String)](#3-task-id-type-integer-to-uuid-string)
  4. [Task Field Renamed (`done` to `completed`)](#4-task-field-renamed-done-to-completed)
  5. [Required `project_id` on Creation](#5-required-project_id-on-creation)
  6. [Response Envelope on List Endpoints (Pagination)](#6-response-envelope-on-list-endpoints-pagination)
- [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
- [Upgrading the Zrb CLI](#upgrading-the-zrb-cli)

---

## Breaking Changes Summary

| # | Change | Impact Area |
|---|---|---|
| 1 | All endpoints are now prefixed with `/v2/` | Base URL & Routing |
| 2 | Authentication header changed from `X-Auth-Token` to `Authorization: Bearer` | Security / Headers |
| 3 | Task `id` type changed from integer to UUID string | Data Model / Schema |
| 4 | Task field `done` renamed to `completed` | Data Model / Schema |
| 5 | Task creation now requires a `project_id` field | API Requests (POST) |
| 6 | List endpoints return a paginated envelope instead of a bare array | API Responses (GET) |

---

## Breaking Changes & Examples

### 1. Base URL Endpoint Prefix `/v2/`

All endpoints are now prefixed with `/v2/` to support versioning. Legacy v1 routes without the `/v2/` prefix are no longer supported.

#### Code Examples

##### **Before (v1):**
```http
GET /tasks HTTP/1.1
Host: api.zrb.local
```

##### **After (v2):**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.local
```

---

### 2. Authentication Header (`X-Auth-Token` to `Bearer` Token)

Authentication has been standardardized to use standard Bearer tokens inside the `Authorization` header. The custom `X-Auth-Token` header is deprecated; requests using the old header will receive an `HTTP 401 Unauthorized` response.

#### Code Examples

##### **Before (v1):**
```http
GET /tasks HTTP/1.1
X-Auth-Token: secret_api_key_v1
```

##### **After (v2):**
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer secret_api_token_v2
```

---

### 3. Task `id` Type (Integer to UUID String)

To allow offline generation and better scale across distributed systems, the Task identifier (`id`) type has transitioned from an auto-incrementing integer to a standard UUID string. 

Ensure your client-side data stores, model schemas, and variable types are updated to handle string-based UUIDs instead of integers.

#### Code Examples

##### **Before (v1 Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

##### **After (v2 Task Object):**
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

The boolean field representing completion status has been renamed from `done` to `completed` for improved linguistic alignment with standard API patterns.

*Note: Update requests (`PUT`) must also use `completed` instead of `done`.*

#### Code Examples

##### **Before (v1 PUT Request):**
```json
{
  "title": "Updated title",
  "done": true
}
```

##### **After (v2 PUT Request):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required `project_id` on Creation

Since tasks are now organized within parent projects, creating a task (`POST /v2/tasks`) now requires an associated `project_id` string. Omitting `project_id` from the payload will yield an `HTTP 422 Unprocessable Entity` error.

#### Code Examples

##### **Before (v1 POST Request):**
```json
{
  "title": "New task title"
}
```

##### **After (v2 POST Request):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Response Envelope on List Endpoints (Pagination)

The list tasks endpoint (`GET /v2/tasks`) no longer returns a bare JSON array. To support cursor-based pagination, it now returns a paginated JSON envelope containing metadata (`total` and `next_cursor`) alongside the items list.

Clients must retrieve task items from the `.items` property. To fetch subsequent pages, supply the cursor using the `?cursor=<next_cursor>` query parameter.

#### Code Examples

##### **Before (v1 List Tasks Response):**
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

##### **After (v2 List Tasks Response):**
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

Follow this checklist to successfully migrate your application from Zrb Task API v1 to v2:

- [ ] **Update Base URLs:** Append `/v2/` to all API client routing configurations and requests.
- [ ] **Revamp Authentication:** Transition authentication headers from `X-Auth-Token: <api_key>` to `Authorization: Bearer <api_token>`.
- [ ] **Adjust Client Schemas for UUIDs:** Update local databases, types, and model mappings for `id` from `integer` to `string`.
- [ ] **Rename Status Fields:** Search your codebase for references to `done` and update them to `completed` for both serialization and deserialization.
- [ ] **Inject `project_id` into Creation Pipelines:** Ensure any interface or automated process creating tasks provides a valid `project_id`.
- [ ] **Refactor List Parsing:** Update your API client code to expect a JSON object instead of a bare array, parsing `items` from the nested `.items` list.
- [ ] **Implement Pagination Handling (Optional):** Update list loops to respect `next_cursor` and page through larger datasets as needed.

---

## Upgrading the Zrb CLI

To get the latest v2 version of the Zrb CLI, run the following upgrade commands:

### Using pipx (Recommended)
```bash
pipx upgrade zrb
```

### Using pip
```bash
pip install --upgrade zrb
```
