# Zrb Task API — v2 Migration Guide

Welcome to the Zrb Task API v2 migration guide. Version 2 introduces key feature additions, including projects, improved pagination, and more robust security standards. 

This guide details all breaking changes between v1 and v2, and provides before/after code examples to help you seamlessly migrate your existing client integrations.

---

## Table of Contents
1. [Breaking Changes Summary](#breaking-changes-summary)
2. [Detailed Breaking Changes and Examples](#detailed-breaking-changes-and-examples)
   - [1. Endpoint Prefix Change (`/v2/`)](#1-endpoint-prefix-change-v2)
   - [2. Authentication Header Change](#2-authentication-header-change)
   - [3. Task ID Type Change (Integer to UUID)](#3-task-id-type-change-integer-to-uuid)
   - [4. Task Field Rename (`done` to `completed`)](#4-task-field-rename-done-to-completed)
   - [5. Task Creation Now Requires `project_id`](#5-task-creation-now-requires-project_id)
   - [6. List Endpoints Return Paginated Envelope](#6-list-endpoints-return-paginated-envelope)
3. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
4. [Upgrade Command](#upgrade-command)

---

## Breaking Changes Summary

If you are currently integrated with the v1 API, you must address the following breaking changes to maintain functionality under v2:

| Change | Impact Area | Description |
| :--- | :--- | :--- |
| **1. Endpoint Prefix** | API Request Routing | All endpoints are now namespaced under the `/v2/` prefix. |
| **2. Auth Header** | API Authentication | Header changed from `X-Auth-Token` to `Authorization: Bearer <token>`. |
| **3. Task ID Format** | Data Types & Schema | Task `id` is now a 36-character UUID string instead of an auto-incrementing integer. |
| **4. Field Rename** | Serialization / Deserialization | The task status field `done` has been renamed to `completed`. |
| **5. Required Project Association** | Task Creation (`POST`) | Creating a task now requires specifying an associated `project_id`. |
| **6. List Payload Envelope** | Response Parsing & Pagination | List endpoints now return a structured, cursor-paginated envelope instead of a bare JSON array. |

---

## Detailed Breaking Changes and Examples

### 1. Endpoint Prefix Change (`/v2/`)

To prevent conflicts and ensure a smooth migration path, all v2 endpoints have been prefixed with `/v2/`. Legacy endpoints without the prefix are deprecated and will not work with v2 features.

#### Before (v1)
Endpoints are called directly at the root path:
```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

#### After (v2)
All endpoints must include the `/v2/` path prefix:
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header Change

Authentication has been standardized to use the industry-standard `Bearer` token scheme inside the `Authorization` header.

* **Behavior Change**: Requests using the legacy `X-Auth-Token` header will fail and return `HTTP 401 Unauthorized`.

#### Before (v1)
```http
X-Auth-Token: 123456abcdef
```

```bash
curl -H "X-Auth-Token: 123456abcdef" https://api.zrb.dev/tasks
```

#### After (v2)
```http
Authorization: Bearer 123456abcdef
```

```bash
curl -H "Authorization: Bearer 123456abcdef" https://api.zrb.dev/v2/tasks
```

---

### 3. Task ID Type Change (Integer to UUID)

To support decentralized ID generation and multi-project tasks, the `id` field has been changed from an auto-incrementing integer to a UUID string.

* **Behavior Change**: Any database schemas, client models, routers, or type systems expecting integer IDs must be updated to handle string-based UUIDs.

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

The field representing the completion status of a task has been renamed from `done` to `completed` to match naming conventions across related services.

* **Behavior Change**: You must update JSON parsers, frontend state definitions, and request payloads for creating and updating tasks.

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

### 5. Task Creation Now Requires `project_id`

With the introduction of project scoping in v2, every task must belong to a parent project.

* **Behavior Change**: The `project_id` field is now mandatory in the request body of `POST /v2/tasks`. Omitting this field will result in an `HTTP 422 Unprocessable Entity` validation error.

#### Before (v1)
```bash
curl -X POST -H "X-Auth-Token: 123456abcdef" \
     -H "Content-Type: application/json" \
     -d '{"title": "Buy milk"}' \
     https://api.zrb.dev/tasks
```

#### After (v2)
```bash
curl -X POST -H "Authorization: Bearer 123456abcdef" \
     -H "Content-Type: application/json" \
     -d '{"title": "Buy milk", "project_id": "proj_abc123"}' \
     https://api.zrb.dev/v2/tasks
```

---

### 6. List Endpoints Return Paginated Envelope

To prevent performance issues when listing large quantities of tasks, `GET /v2/tasks` no longer returns a bare JSON array. It now returns a paginated envelope object and uses cursor-based pagination.

* **Behavior Change**: Clients must extract list elements from the `.items` array. They should also implement pagination logic using the `.next_cursor` property and the `cursor` query parameter.

#### Before (v1)
Legacy list endpoint response:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

#### After (v2)
Paginated list response:
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

To fetch the next page, pass the `next_cursor` value as a query parameter:
```bash
curl -H "Authorization: Bearer 123456abcdef" \
     "https://api.zrb.dev/v2/tasks?cursor=cursor_xyz&limit=20"
```

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your codebases and clients from v1 to v2:

- [ ] **1. Upgrade Zrb CLI**: Update your local and production environments to the latest version of the CLI (see command below).
- [ ] **2. Refactor Data Models & Schemas**:
  - Update local storage, cache, or database schemas where Task IDs are defined: change type from `integer` to `string` (UUID).
  - Rename task completion state fields from `done` to `completed`.
  - Add support for the new `project_id` field on tasks.
- [ ] **3. Update Client Authentication**:
  - Locate all outbound API request setups.
  - Remove the custom `X-Auth-Token` header.
  - Implement standard `Authorization` headers using the `Bearer <token>` format.
- [ ] **4. Namespace Endpoint URIs**:
  - Prepend all legacy task routes with the `/v2/` prefix (e.g., replace `/tasks` with `/v2/tasks`).
- [ ] **5. Refactor Task Creation Requests**:
  - Ensure all `POST` operations payload include a valid `project_id`.
- [ ] **6. Rewrite Response Parsers**:
  - Locate list handlers where task collections are parsed.
  - Modify parsers to extract arrays from the `.items` property instead of iterating directly over the top-level payload.
  - Implement pagination helpers that read `.next_cursor` and append `?cursor=<cursor_value>` to fetch subsequent pages.
- [ ] **7. Verify & Test**:
  - Run integration and unit tests to ensure compatibility.
  - Perform end-to-end user flows representing creation, listing, updating, and deletion.

---

## Upgrade Command

To update the Zrb CLI to version 2, execute the standard package upgrade command:

```bash
pip install --upgrade zrb
```
