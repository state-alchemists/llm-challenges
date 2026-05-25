# Zrb Task API v2 Migration Guide

Welcome to the Zrb Task API v2. This version introduces first-class projects, cursor-based pagination for high performance, and standardizes authentication protocols. To support these features, several breaking changes have been introduced. 

This guide is designed for experienced developers who are currently using Zrb Task API v1. It provides a comprehensive reference of all breaking changes, detailed before-and-after comparisons, and a step-by-step migration checklist.

---

## Table of Contents
1. [Global Endpoint Prefix Change](#1-global-endpoint-prefix-change)
2. [Authentication Header Upgrade](#2-authentication-header-upgrade)
3. [Identifier Type Migration (Integer to UUID)](#3-identifier-type-migration-integer-to-uuid)
4. [Field Renaming (`done` to `completed`)](#4-field-renaming-done-to-completed)
5. [Required Project Association](#5-required-project-association)
6. [Paginated List Envelope Response](#6-paginated-list-envelope-response)
7. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
8. [Upgrading the CLI](#upgrading-the-cli)

---

## 1. Global Endpoint Prefix Change

To support versioning and isolate v1 legacy consumers, all endpoint routes have been prefixed with `/v2/`. Legacy `/tasks` paths are now deprecated and will not respond to v2-specific logic.

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

## 2. Authentication Header Upgrade

For enhanced security and compliance with OAuth 2.0 standards, the custom `X-Auth-Token` header has been removed. All API clients must now authenticate using the standard HTTP `Authorization` header with a `Bearer` token schema. Requesting a v2 endpoint with `X-Auth-Token` will return an HTTP `401 Unauthorized` status.

### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: zrb_api_key_v1_xyz123
```

### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer zrb_api_key_v2_abc987
```

---

## 3. Identifier Type Migration (Integer to UUID)

To facilitate distributed systems integration, ID collision avoidance, and offline task creation, the Task `id` type has been changed from an auto-incrementing integer to a standard UUID string. If your database schemas, local models, or typescript definitions represent task IDs as integers, you must migrate them to support variable-width string types.

### Before (v1 Task Schema)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2 Task Schema)
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

To align with modern API guidelines and better match our language SDKs, the boolean field `done` has been renamed to `completed`. Any update operations via `PUT` and serialization/deserialization routines must adapt to this property rename.

### Before (v1 Task Update)
```json
PUT /tasks/42 HTTP/1.1
Content-Type: application/json

{
  "title": "Updated title",
  "done": true
}
```

### After (v2 Task Update)
```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Content-Type: application/json

{
  "title": "Updated title",
  "completed": true
}
```

---

## 5. Required Project Association

With the introduction of workspace and project hierarchies in v2, tasks can no longer exist in a global, unassociated namespace. Every task creation payload must supply a valid, existing `project_id`. Failing to include this parameter will result in an HTTP `422 Unprocessable Entity` error.

### Before (v1 Task Creation)
```json
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

### After (v2 Task Creation)
```json
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

## 6. Paginated List Envelope Response

In v1, calling `GET /tasks` returned a flat, unpaginated JSON array containing all tasks. To prevent high-volume database performance degradation and scale infinitely, v2 wraps list responses in a paginated envelope containing `items`, `total`, and `next_cursor`. Cursor-based navigation is supported via the `?cursor=<cursor>` query parameter.

### Before (v1 List Response)
```json
[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:00:00Z"
  },
  {
    "id": 2,
    "title": "Ship v1",
    "done": true,
    "created_at": "2024-01-15T10:15:00Z"
  }
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
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Step-by-Step Migration Checklist

Follow this systematic roadmap to transition your integration safely:

- [ ] **Audit all Endpoint URIs**: Search your codebase for references to the `/tasks` route. Update them to include the `/v2/` prefix.
- [ ] **Update HTTP Client Headers**: Standardize your authorization headers, replacing `X-Auth-Token` keys with standard `Authorization: Bearer <token>` entries.
- [ ] **Migrate Client & Server Data Models**: Update model properties and type signatures to change task IDs from `int`/`number` to `string` (UUIDs).
- [ ] **Refactor Database Schemas**: Perform a database migration if you are storing task IDs locally. Alter the column type to accommodate 36-character UUID strings.
- [ ] **Refactor Boolean Field Mapping**: Update field mapping, serialization, and JSON decoding files to map the old `done` attribute to `completed`.
- [ ] **Inject project_id Parameter**: Modify all your task creation modules to fetch and include a valid `project_id` in POST body payloads.
- [ ] **Refactor Collection Parsing**: Update code blocks parsing list responses. Extract items from `response.items` instead of iterating over the raw HTTP response body directly. Add pagination logic utilizing `next_cursor` if fetching multiple pages.
- [ ] **Conduct Integration Verification**: Deploy code to a test/sandbox environment and perform a complete integration run covering Task creation, retrieval, updates, list paging, and deletion.

---

## Upgrading the CLI

To update your developer environment and local tooling to the latest Zrb v2 CLI, execute the upgrade command:

```bash
pip install --upgrade zrb
```
