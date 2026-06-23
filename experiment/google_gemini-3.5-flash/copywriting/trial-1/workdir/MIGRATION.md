# Zrb CLI v1 to v2 Migration Guide

## Overview

The Zrb CLI is releasing v2, which introduces several major enhancements to improve scalability, support project-based organization, and enforce stricter security policies. To accommodate these features—including first-class projects, cursor-based pagination, and Bearer token authentication—several breaking changes have been introduced.

This guide provides a comprehensive walkthrough for experienced developers migrating their integrations, scripts, and client applications from Zrb v1 to v2. 

---

## Summary of Breaking Changes

Here is a summary of the key breaking changes between Zrb v1 and Zrb v2:

1. **Endpoint Path Prefixing:** All endpoints are now prefixed with `/v2/` (e.g., `/tasks` is now `/v2/tasks`).
2. **Authentication Header:** The custom `X-Auth-Token` header has been replaced by the standard `Authorization` header with a `Bearer` token.
3. **Identifier Data Type:** Task `id` types have shifted from auto-incrementing integers to UUID strings.
4. **Task State Field Rename:** The task boolean field `done` has been renamed to `completed`.
5. **Required Project ID on Creation:** Task creation payloads must now include a valid `project_id`.
6. **List Pagination Envelope:** The list tasks endpoint no longer returns a bare JSON array; it returns a paginated envelope.

---

## Detailed Breaking Changes

### 1. Endpoint Path Prefixing

In Zrb v2, all API endpoints are now prefixed with `/v2/` (e.g. `/v2/tasks`) and task creation requires a valid `project_id` parameter. This versioning prefix ensures that v1 and v2 traffic can be routed cleanly, preventing collision.

**Before (v1 API):**
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key
```

**After (v2 API):**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token
```

---

### 2. Authentication Header Change

The authentication mechanism has been updated: the previous `X-Auth-Token` header is deprecated, and you must now pass a Bearer token via the `Authorization` header. Requests using the legacy `X-Auth-Token` header will return a `401 Unauthorized` response on v2 endpoints.

**Before (v1 API):**
```http
X-Auth-Token: your_api_key
```

**After (v2 API):**
```http
Authorization: Bearer your_api_token
```

---

### 3. Task ID Type Shift

The task identifier field `id` has been changed from an auto-incrementing integer to a string UUID. If your application parses task identifiers or uses integer-only validation schemas (e.g., in TypeScript or Pydantic models), you must update them to expect standard UUID string representations.

**Before (v1 API):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 API):**
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

### 4. Task State Field Rename

The task boolean status field `done` has been renamed to `completed` in v2. Any client code reading or mutating task state must use the new field name. Using `done` in update requests will have no effect, and reading `done` from response objects will yield undefined/missing values.

**Before (v1 API):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 API):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required Project ID on Task Creation

Creating a task now requires a valid `project_id` string field in the JSON payload. This is a consequence of the new project-based organization structure in Zrb v2. Omitting this field during task creation will result in a `422 Unprocessable Entity` error.

**Before (v1 API):**
```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2 API):**
```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Response Pagination Envelope

The task list endpoint (`GET /v2/tasks`) now returns a structured, paginated envelope containing pagination metadata instead of a bare JSON array of tasks. This is essential for scaling performance as your task list grows.

The new structure provides `items` (the list of task objects), `total` (the total number of matching items), and `next_cursor` (the string token to pass to the next page request as `?cursor=<next_cursor>`).

**Before (v1 API):**
```json
[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

**After (v2 API):**
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
  "next_cursor": null
}
```

---

## Step-by-Step Migration Checklist

To successfully transition your client applications or scripts to Zrb CLI v2, follow this step-by-step migration checklist:

- [ ] **Step 1: Prefix Endpoint Paths:** Update all API requests to use the new `/v2` prefix in URL paths.
- [ ] **Step 2: Update Authentication:** Switch authentication headers from the deprecated `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
- [ ] **Step 3: Update Identifier Data Type:** Update task ID schema validation and parsing code to handle string UUIDs instead of integers.
- [ ] **Step 4: Rename Status Fields:** Update all code referencing the task status field from `done` to `completed` for reading and writing data.
- [ ] **Step 5: Provide Project ID on Creation:** Add the required `project_id` string field to task creation payload structures.
- [ ] **Step 6: Handle Paginated Responses:** Update task listing code to parse the paginated list envelope (`items`, `total`, `next_cursor`) instead of treating the response as a bare array.
- [ ] **Step 7: Run Integration Tests:** Execute test suites to verify full compatibility.

---

## How to Upgrade

To upgrade the Zrb CLI to the latest v2 version, run the following command in your terminal:

```bash
pip install --upgrade zrb
```
