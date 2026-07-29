# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary steps and changes to migrate your existing Zrb CLI v1 integrations to the new v2 API. Zrb CLI v2 introduces significant improvements, including project support, enhanced pagination, and a more robust authentication mechanism. This guide will help you understand and implement the breaking changes with minimal disruption.

## Overview of Breaking Changes

Zrb CLI v2 introduces several breaking changes that impact endpoint paths, authentication, data structures, and API responses:

1.  **Endpoint Paths:** All API endpoints are now prefixed with `/v2/`.
2.  **Authentication Header:** The authentication mechanism has changed from `X-Auth-Token` to a `Bearer` token in the `Authorization` header.
3.  **Task ID Type:** The `id` field for Task objects has transitioned from an integer to a UUID string.
4.  **Task Field Renaming:** The `done` field in the Task object has been renamed to `completed`.
5.  **Task Creation Requirement:** Creating new tasks now requires a `project_id`.
6.  **Paginated List Responses:** List endpoints now return a paginated envelope instead of a bare array of items.

---

## Detailed Breaking Changes and Migration Steps

### 1. Endpoint Path Prefix

All v2 API endpoints are now prefixed with `/v2/`. This ensures versioning and allows for future API evolution.

**Before (v1 - List Tasks):**
```
GET /tasks
```

**After (v2 - List Tasks):**
```
GET /v2/tasks
```

**Migration:** Update all your API calls to include the `/v2/` prefix immediately after the base URL.

### 2. Authentication Header

The authentication header has been updated for improved security and standardization. Instead of `X-Auth-Token`, v2 uses a standard `Bearer` token.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

**Migration:** Change your authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`. Requests using the old header will result in an HTTP 401 Unauthorized error.

### 3. Task ID Type Change

The `id` field for Task objects has changed from an integer to a UUID string, providing a more robust and universally unique identifier.

**Before (v1 - Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 - Task Object):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Migration:** If your application stores or processes Task IDs, you must update your data types and logic to handle UUID strings instead of integers. This primarily affects `GET /tasks/{id}` and `PUT /tasks/{id}` calls where the ID is part of the URL path.

### 4. Task Field Renaming: `done` to `completed`

The boolean field indicating a task's completion status has been renamed for clarity.

**Before (v1 - Update Task request body):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 - Update Task request body):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

**Migration:** Replace all occurrences of the `done` field with `completed` in your Task object serialization and deserialization logic, especially in `POST` and `PUT` requests.

### 5. Task Creation Requires `project_id`

In v2, tasks are now associated with projects. Therefore, `project_id` is a mandatory field when creating a new task.

**Before (v1 - Create Task request body):**
```json
{
  "title": "New task title"
}
```

**After (v2 - Create Task request body):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Migration:** When creating tasks via `POST /v2/tasks`, you must now include a `project_id` in the request body. Omitting this field will result in an HTTP 422 Unprocessable Entity error. Ensure you have a valid `project_id` to associate with new tasks.

### 6. List Endpoints Return Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) now return a paginated response wrapped in an envelope object, providing metadata like `total` items and a `next_cursor` for fetching subsequent pages.

**Before (v1 - List Tasks response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 - List Tasks response):**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Migration:** Adjust your code to parse the `items` array from within the response envelope. Implement pagination logic using the `cursor` query parameter and the `next_cursor` value from the response for fetching subsequent pages.

---

## Migration Checklist

Follow these steps to migrate your Zrb CLI integrations to v2:

1.  [ ] **Update Endpoint Paths:** Prefix all API calls with `/v2/`.
2.  [ ] **Revise Authentication:** Change `X-Auth-Token` headers to `Authorization: Bearer <your_api_token>`.
3.  [ ] **Adjust Task ID Handling:** Update your code to expect and handle UUID strings for task IDs instead of integers.
4.  [ ] **Rename Task Completion Field:** Change all references from `done` to `completed` in your Task object serialization/deserialization.
5.  [ ] **Add `project_id` to Task Creation:** Ensure all `POST /v2/tasks` requests include a valid `project_id` in the request body.
6.  [ ] **Update List Response Parsing:** Modify your logic to extract task items from the `items` array within the new paginated envelope response.
7.  [ ] **Implement Pagination (Optional but Recommended):** Integrate `cursor` and `limit` query parameters for handling large lists.

## Upgrade Zrb CLI

To upgrade your Zrb CLI installation to the latest v2 version, run the following command:

```bash
zrb upgrade --v2
```
