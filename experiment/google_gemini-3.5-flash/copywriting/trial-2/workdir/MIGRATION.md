# Zrb CLI v2 Migration Guide

Welcome to the Zrb CLI v2 migration guide. This document is designed to help experienced developers transition their existing v1 integrations to the new v2 API. 

The v2 release introduces native project isolation, robust cursor-based pagination, and a more secure, industry-standard authentication mechanism. Consequently, v2 contains several breaking changes that will require modifications to your application logic, payload schemas, and database definitions.

---

## Breaking Changes Summary

1. [Base URL Endpoint Prefix Change (`/v2/`)](#1-base-url-endpoint-prefix-change)
2. [Authentication Header Standardized to Bearer Token](#2-authentication-header-standardized-to-bearer-token)
3. [Task ID Type Migrated from Integer to UUID String](#3-task-id-type-migrated-from-integer-to-uuid-string)
4. [Task Field `done` Renamed to `completed`](#4-task-field-done-renamed-to-completed)
5. [Task Creation Now Requires `project_id`](#5-task-creation-now-requires-project_id)
6. [List Endpoints Enveloped for Pagination](#6-list-endpoints-enveloped-for-pagination)

---

## Breaking Changes in Detail

### 1. Base URL Endpoint Prefix Change
All endpoints now reside under a `/v2/` namespace. Directly querying the legacy v1 endpoints will either yield outdated resources or result in HTTP routing errors.

#### Before
```http
GET /tasks
GET /tasks/123
POST /tasks
```

#### After
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
```

---

### 2. Authentication Header Standardized to Bearer Token
Authentication has been hardened. The legacy custom header `X-Auth-Token` has been deprecated and replaced with the industry-standard `Authorization: Bearer <token>` header.

* **Impact:** Sending requests using `X-Auth-Token` will return an **HTTP 401 Unauthorized** error.

#### Before (v1 Request Headers)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: zrb_token_987654321
```

#### After (v2 Request Headers)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer zrb_token_987654321
```

---

### 3. Task ID Type Migrated from Integer to UUID String
To support decentralized task creation and prevent ID-enumeration vulnerabilities, the task resource `id` type has been changed from an auto-incrementing integer to a 36-character RFC 4122 UUID v4 string.

* **Impact:** Client-side parsing code, type definitions, and local databases referencing tasks must update their schemas to treat `id` as a string rather than an integer.

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

### 4. Task Field `done` Renamed to `completed`
To improve semantic clarity across endpoints, the boolean field `done` has been renamed to `completed`.

* **Impact:** This change affects the JSON payload in both **Task retrieval responses** and **Update Task requests (`PUT`)**.

#### Before (v1 Update Request & Response)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2 Update Request & Response)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task Creation Now Requires `project_id`
Tasks in v2 must belong to a specific project. When invoking `POST /v2/tasks`, you must explicitly supply a valid `project_id`.

* **Impact:** Omitting the `project_id` field in the request body will result in an **HTTP 422 Unprocessable Entity** validation error.

#### Before (v1 Task Creation Payload)
```json
{
  "title": "New task title"
}
```

#### After (v2 Task Creation Payload)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Endpoints Enveloped for Pagination
To handle high-volume data cleanly, list endpoints no longer return a bare JSON array. They now return a paginated JSON envelope containing pagination metadata alongside the task records.

The endpoint supports two optional query parameters:
* `limit` — Maximum results per page (defaults to 20).
* `cursor` — Cursor token to fetch the next page of results.

#### Before (v1 `GET /tasks` Response)
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

#### After (v2 `GET /v2/tasks` Response)
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

Follow these steps to upgrade your codebase and integrations:

- [ ] **Step 1: Upgrade the CLI/SDK** — Run the upgrade command to install the latest v2 version of the Zrb CLI.
- [ ] **Step 2: Update Endpoints** — Update all API routing references and base URLs to include the `/v2/` prefix.
- [ ] **Step 3: Modify Authentication** — Change your HTTP request headers to use `Authorization: Bearer <your_token>` instead of `X-Auth-Token`.
- [ ] **Step 4: Update Database & Models (ID Type)** — Update your database schema, model definitions, and parsing code to handle `id` as a UUID string instead of an integer.
- [ ] **Step 5: Rename Field References** — Refactor your models, state managers, and views to map `done` to `completed`.
- [ ] **Step 6: Inject Project Associations** — Update your task creation logic to include a required `project_id` parameter.
- [ ] **Step 7: Adapt Response Decoders** — Modify your GET list decoding structures to extract tasks from the `.items` array of the paginated envelope instead of parsing a bare array directly.
- [ ] **Step 8: Implement Cursor Pagination** — (Optional but recommended) Update your user interface or list consumers to handle page traversal using the `next_cursor` pointer.

---

## Upgrade Command

To update the Zrb CLI to the latest v2-compliant release, execute the following command in your terminal:

```bash
pip install --upgrade zrb
```
