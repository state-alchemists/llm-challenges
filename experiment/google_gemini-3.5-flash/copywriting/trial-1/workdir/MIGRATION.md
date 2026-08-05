# Zrb CLI v2 Migration Guide

Welcome to the Zrb CLI v2 Migration Guide. This document is designed to help developers transition their existing integrations and clients from Zrb CLI v1 to the newly released v2 API.

Zrb CLI v2 introduces several architectural enhancements, including the concept of projects, improved list pagination, and modern, standardized authentication standards. While these changes make the CLI more robust, scalable, and secure, they introduce several breaking changes that are incompatible with v1 clients.

---

## Overview of Key Changes

The transition to v2 involves updating API endpoints, changing request headers, adjusting payload formats, and refactoring how identifiers and boolean status fields are processed. 

### Why Upgrade to v2?
- **Project Scoping:** Tasks are now scoped under explicit project containers, preventing global task clutter and enabling multi-tenant workflows.
- **Stricter Security:** Standardized Bearer token authentication ensures better compatibility with API gateways and OAuth2 providers.
- **Scalable Pagination:** Bare array listings have been replaced with cursor-based pagination, protecting both clients and servers from memory exhaustion on large datasets.

---

## Breaking Changes Reference

This section details every breaking change between v1 and v2, complete with before and after code examples.

### 1. Endpoint Prefix Change

In v1, the API endpoints were exposed directly at the root path of the service. All endpoints now use the `/v2` prefix, and creating a task now requires a valid `project_id` parameter.

#### Before (v1 Endpoints)
```http
GET /tasks HTTP/1.1
POST /tasks HTTP/1.1
GET /tasks/42 HTTP/1.1
```

#### After (v2 Endpoints)
```http
GET /v2/tasks HTTP/1.1
POST /v2/v2/tasks HTTP/1.1
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
```

*(Note: Every API endpoint is prefixed with `/v2`, such as `/v2/tasks`.)*

---

### 2. Authentication Header Change

Authentication has been modernized to adhere to RFC 6750 standards. The authentication header has changed from `X-Auth-Token` to a standard `Authorization` header with a `Bearer` token. Requests sent with the old `X-Auth-Token` header will now fail and receive an HTTP 401 Unauthorized response.

#### Before (v1 Auth Header)
```http
GET /tasks HTTP/1.1
X-Auth-Token: v1_secret_api_key_here
```

#### After (v2 Auth Header)
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer v2_secret_api_token_here
```

---

### 3. Task ID Type Change

To support decentralized ID generation and avoid predictable sequential IDs, the task identifier type has been upgraded. In v2, the task `id` field type has been updated from an integer to a standard UUID string. 

Clients parsing the task ID as an integer must update their schema definitions and routing models to accept 36-character UUID strings.

#### Before (v1 Integer ID)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2 UUID ID)
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

### 4. Task Status Field Rename

The task completion status field has been renamed to align with industry conventions. The task completion field `done` is renamed to `completed` in v2. Both read responses and write payloads must use this new field name.

#### Before (v1 Update Payload)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2 Update Payload)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required Project ID on Creation

In v2, all tasks must belong to a specific project. A valid `project_id` is now a required parameter when creating tasks. Omitting this field in a `POST /v2/tasks` request will result in an HTTP 422 Unprocessable Entity error.

#### Before (v1 Creation Payload)
```json
{
  "title": "New task title"
}
```

#### After (v2 Creation Payload)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Endpoints Pagination Envelope

In v1, list endpoints returned a bare JSON array. In v2, list endpoints now return a paginated envelope containing an items array, a total count, and a pagination cursor. To fetch subsequent pages, you must pass the cursor as a query parameter.

#### Before (v1 Bare Array Response)
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

#### After (v2 Paginated Envelope Response)
```json
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

To fetch the next page, append the cursor to your query params:
```http
GET /v2/tasks?cursor=cursor_xyz&limit=20 HTTP/1.1
Authorization: Bearer v2_secret_api_token_here
```

---

## Step-by-Step Migration Checklist

Follow this checklist to successfully migrate your application from Zrb CLI v1 to v2:

- [ ] **Step 1:** Run the upgrade command to install the latest v2 version of the Zrb CLI.
- [ ] **Step 2:** Locate all HTTP clients or API wrappers referencing the `/tasks` endpoints.
- [ ] **Step 3:** Prefix all endpoint paths with `/v2` (e.g., change `/tasks` to `/v2/tasks`).
- [ ] **Step 4:** Replace the `X-Auth-Token: <token>` header with `Authorization: Bearer <token>` in your request configuration.
- [ ] **Step 5:** Modify database schemas and client-side models to treat the task `id` field as a UUID string rather than an integer.
- [ ] **Step 6:** Audit all codebases for references to the `.done` attribute and rename them to `.completed` (this applies to both JSON serialization and deserialization).
- [ ] **Step 7:** Retrieve or create a project ID in Zrb CLI, and ensure every task creation payload (`POST /v2/tasks`) includes the required `"project_id"` key.
- [ ] **Step 8:** Refactor your list parsing logic. Instead of parsing a root JSON array, deserialize the object envelope and extract the array from the `"items"` field.
- [ ] **Step 9:** Implement pagination logic to handle `"next_cursor"` and make subsequent requests using the `?cursor=` query parameter.
- [ ] **Step 10:** Run integration tests to verify successful HTTP 200, 201, and 204 responses, and check that missing `project_id` results in HTTP 422.

---

## Upgrade Command

To upgrade the Zrb CLI tool to the latest v2 release, execute the following command in your terminal:

```bash
pip install --upgrade zrb
```

If you are managing your dependencies using Poetry, run:

```bash
poetry add zrb@latest
```
