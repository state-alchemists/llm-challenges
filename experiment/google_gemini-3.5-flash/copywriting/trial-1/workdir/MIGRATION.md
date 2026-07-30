# Zrb CLI v1 to v2 Migration Guide

Welcome to the Zrb CLI v2 Migration Guide. This document provides a comprehensive, step-by-step walkthrough for migrating your existing integrations, API clients, and application layers from the Zrb Task API v1 to the newly released Zrb Task API v2.

Version 2 introduces major structural enhancements, including first-class project support, cursor-based pagination, and a transition to standard UUID format for entity identifiers. These upgrades improve performance, reliability, and scalability, but introduce several breaking changes that require immediate updates to your code.

---

## Overview of Major Changes

Below is a high-level summary of the key breaking changes introduced in Zrb v2:

1. **Endpoint Paths Prefix**: All endpoint paths are now prefixed with `/v2/` to ensure clean version routing.
2. **Standardized Authentication**: The legacy custom `X-Auth-Token` header is replaced with standard HTTP Bearer token authentication in the `Authorization` header.
3. **UUID Task Identifiers**: Task identifiers have been upgraded from sequential integers to standard UUID strings.
4. **Boolean Field Renaming**: The task status field `done` has been renamed to `completed` for consistency and semantic clarity.
5. **Mandatory Project Scoping**: All tasks are now grouped under projects. Creating a task requires a valid `project_id`.
6. **Paginated Envelope Responses**: List endpoints now return a structured JSON envelope containing metadata and a next page cursor, rather than a bare array.

---

## Detailed Breaking Changes and Migration Steps

### 1. Endpoint Prefixing (`/v2/`)

All API routes are now systematically routed through the `/v2` namespace. Any requests hitting the old v1 endpoints without this prefix will return resource not found or deprecation errors.

**Before (v1 Endpoints):**
```http
GET /tasks
POST /tasks
PUT /tasks/{id}
```

**After (v2 Endpoints):**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
```

---

### 2. Authentication Header Refactoring (`Authorization: Bearer`)

We have updated the authentication layer to enforce standard token practices. You must replace the custom `X-Auth-Token` header with the standard HTTP `Authorization` header containing a `Bearer` token. Requests utilizing the legacy header will be rejected with an HTTP 401 Unauthorized status.

**Before (v1 Headers):**
```http
X-Auth-Token: your_api_key_v1
```

**After (v2 Headers):**
```http
Authorization: Bearer your_api_token_v2
```

---

### 3. Task ID Type Upgraded to UUID

In v2, the `id` field of a task is represented as a globally unique `uuid` string instead of a sequential integer. Update your database schemas, internal data structures, and URL parsers to accommodate 36-character UUID strings instead of sequence integers.

**Before (v1 Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 Task Object):**
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

### 4. Field Renaming (`done` to `completed`)

To better reflect task state semantics and adhere to industry standards, the boolean field has been renamed from `done` to `completed`. Ensure that all frontend UI components, database queries, and serializer mappings are updated accordingly to avoid null or missing field errors.

**Before (v1 JSON Field):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 JSON Field):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Mandatory Project Scoping (`project_id`)

All tasks are now stored within a specific project. When sending a payload to the `/v2/tasks` endpoint, specifying the `project_id` field is now strictly required. Omitting the `project_id` in a task creation request will result in an HTTP 422 Unprocessable Entity response.

**Before (v1 POST payload):**
```json
{
  "title": "New task title"
}
```

**After (v2 POST payload):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Envelope Response for List Endpoints

To prevent performance degradation with large collections, the v2 list endpoint (`GET /v2/tasks`) no longer returns a bare JSON array. Instead, it returns a structured JSON envelope with pagination metadata. Clients must extract the task array from the `items` key and use the `next_cursor` key to paginate.

**Before (v1 Bare Array Response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 Paginated Envelope Response):**
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

## Migration Checklist

Ensure your application handles every breaking change by running through this step-by-step migration checklist:

- [ ] **Base URL Prefixing**: Prepend `/v2/` to all API endpoints inside your configuration files.
- [ ] **Authentication Migration**: Replace the custom `X-Auth-Token` headers with standardized `Authorization: Bearer <token>` headers.
- [ ] **Data Model Schema Updates**: Modify your model definitions, schemas, and databases to store and validate 36-character UUID strings instead of sequence integers.
- [ ] **Field Refactoring**: Update all codebases, UI elements, and API client scripts to use `completed` instead of the legacy `done` attribute.
- [ ] **Payload Adjustments**: Update task creation logic to retrieve or default a `project_id` and pass it in the `POST` request payload.
- [ ] **Pagination Logic overhaul**: Refactor task collection processing to extract the collection array from the `items` key of the envelope response and parse the `next_cursor` for paginated requests.
- [ ] **Testing and Validation**: Run comprehensive end-to-end integration tests using the upgraded v2 endpoints.

## Upgrading the Zrb CLI

Once your codebase and integration layers have been updated, you can proceed to upgrade your local installation of the Zrb CLI to the latest major release.

Execute the following package manager command to upgrade:

```bash
pip install --upgrade zrb
```
