# Zrb CLI v2 Migration Guide

Welcome to the Zrb CLI v2 Migration Guide. This document is designed to assist experienced developers in transitioning their applications, integrations, and services from Zrb CLI v1 to the new v2 API release. 

v2 introduces powerful new features—including task projects, cursor-based pagination, and stricter authentication mechanisms—to make your task management pipeline more secure and robust. However, because of these improvements, v2 introduces several breaking changes that are incompatible with v1. This guide details every breaking change, provides clear before-and-after code examples, and offers a step-by-step checklist to ensure a seamless upgrade.

---

## Summary of Breaking Changes

Here is a high-level summary of the breaking changes between v1 and v2:

1. **API Endpoint Prefixing**: All API paths must now be prefixed with `/v2/` instead of `/`.
2. **Authentication Header**: The legacy API key header `X-Auth-Token` has been replaced with standard HTTP Bearer token authentication.
3. **Task ID Format**: Task identifiers are now UUID strings instead of auto-incrementing integers.
4. **Field Renames**: The boolean flag `done` on the Task object has been renamed to `completed`.
5. **Required Project Association**: Creating a task now strictly requires a `project_id`.
6. **Paginated List Responses**: List endpoints now return a structured pagination envelope instead of a bare array.

---

## Breaking Changes Details & Code Examples

### 1. API Endpoint Prefixing & Required Project ID
All endpoints in the new API version have been changed to include the /v2 prefix, and creating a task now requires a project_id.
In v1, you could perform a POST request to `/tasks` with only a task `title`. In v2, you must update the base path to `/v2/tasks` and include a valid `project_id` within the request body. If you omit the `project_id`, the API will return an HTTP 422 Unprocessable Entity error.

**Before (v1 API Request):**
```http
POST /tasks
X-Auth-Token: usr_v1_key_abcdef12345

{
  "title": "Write database migration scripts"
}
```

**After (v2 API Request):**
```http
POST /v2/tasks
Authorization: Bearer usr_v2_token_xyz987

{
  "title": "Write database migration scripts",
  "project_id": "proj_abc123"
}
```

---

### 2. Authentication Header Change
The authentication header changed from X-Auth-Token to Bearer token Authorization.
In v1, clients authenticated by providing their API key in the custom `X-Auth-Token` header. In v2, this header is deprecated. Clients must now use the standard HTTP `Authorization` header with a `Bearer` token scheme. Requests using the old header will be rejected with an HTTP 401 Unauthorized response.

**Before (v1 Header):**
```http
X-Auth-Token: v1_secret_api_key_here
```

**After (v2 Header):**
```http
Authorization: Bearer v2_secret_bearer_token_here
```

---

### 3. Task ID Type Change (Integer to UUID)
The task id type has been changed from an integer in v1 to a UUID string in v2.
To prevent ID enumeration and support decentralized task generation, task identifiers have been upgraded from sequential integers to globally unique UUID strings. If your client-side application or local database schema assumes an integer type for task IDs, you must update those data models to expect a UUID string.

**Before (v1 Schema Example):**
```json
{
  "id": 42,
  "title": "Implement authentication",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 Schema Example):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Implement authentication",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 4. Task Field Rename (`done` to `completed`)
To improve clarity, the task field done has been renamed to completed in v2.
The boolean field indicating task completion status has been updated. The field `done` is no longer supported in request bodies or returned in responses. It has been renamed to `completed`. Update your database models, serializers, and frontend bindings to use this new field name.

**Before (v1 PUT Request):**
```http
PUT /tasks/42
X-Auth-Token: usr_v1_key_abcdef12345

{
  "title": "Implement authentication",
  "done": true
}
```

**After (v2 PUT Request):**
```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
Authorization: Bearer usr_v2_token_xyz987

{
  "title": "Implement authentication",
  "completed": true
}
```

---

### 5. Paginated List Responses (Bare Array to Envelope)
In v1, fetching the list of tasks returned a bare JSON array. In v2, list endpoints return a paginated response envelope with an `items` array, a `total` count, and a `next_cursor` string for cursor-based pagination. If your client parses the API response directly as an array, this change will cause parsing errors.

**Before (v1 GET /tasks Response):**
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

**After (v2 GET /v2/tasks Response):**
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

Follow these steps to migrate your code and database successfully from v1 to v2:

- [ ] **Backup Your Database**: Back up all existing data before performing any schema or record modifications.
- [ ] **Migrate Database Schema**: Change the task ID column type from integer to a string or UUID column.
- [ ] **Generate Projects**: Create default projects in your database to associate with existing tasks.
- [ ] **Assign project_id to Existing Tasks**: Update existing tasks with a valid `project_id` foreign key.
- [ ] **Rename Database Columns**: Rename the `done` boolean column to `completed` in your tables.
- [ ] **Update Application Authentication**: Replace all code references to `X-Auth-Token` with the standard `Authorization: Bearer <token>` header.
- [ ] **Update Request Paths**: Prepend `/v2/` to all API paths in your client endpoints.
- [ ] **Refactor Task Creation Payloads**: Add the required `project_id` to all task creation requests.
- [ ] **Refactor List Parsing**: Change list-handling code to read tasks from the `.items` field of the returned JSON envelope.
- [ ] **Implement Cursor Pagination**: Update list requests to handle the `next_cursor` token and `cursor` query parameters.

---

## Upgrade Command

To upgrade the Zrb CLI library and command line client to the latest version (v2), run the following package manager command:

```bash
pip install --upgrade zrb
```
