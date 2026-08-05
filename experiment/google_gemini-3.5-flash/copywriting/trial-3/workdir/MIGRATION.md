# Zrb Task API — v1 to v2 Migration Guide

Welcome to the official developer migration guide for the Zrb Task API v2 release. This document is designed to help developers who are currently using Zrb Task API v1 transition smoothly to the newly designed v2 API.

The Zrb Task API v2 introduces projects, improved cursor-based pagination, and stricter authentication mechanisms. While these changes bring massive improvements to developer productivity, performance, and security, they introduce several breaking changes that require modifications in your existing v1 clients and database schemas.

---

## Summary of Breaking Changes

Here is a high-level overview of the breaking changes in the Zrb Task API v2:
1. **Global Endpoint Prefixing**: All API endpoints are now prefixed with `/v2/`.
2. **Authentication Header Change**: Changed from `X-Auth-Token` to standard `Authorization: Bearer <token>`.
3. **Task ID Format Change**: Task `id` representation changed from integer to UUID string.
4. **Field Rename**: Task field `done` is renamed to `completed`.
5. **Required Project Association**: Task creation now requires a `project_id` field.
6. **List Pagination Envelope**: List endpoints now return a paginated JSON envelope object instead of a bare JSON array.

---

## Detailed Breaking Changes

### 1. Global Endpoint Prefixing
To support version coexistence and future-proof the platform, all API endpoints are now prefixed with `/v2/` in the path. Legacy v1 endpoints at the root namespace (e.g., `/tasks`) will return HTTP `404 Not Found` in v2.

**Before (v1):**
Endpoints were located at the root namespace:
```http
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**
All endpoints are now prefixed with `/v2/`:
```http
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication Header Change
The authentication header changed in v2 from the custom `X-Auth-Token` to the standard `Authorization` header with a `Bearer` token.
All requests targeting v2 endpoints must utilize the standard Bearer scheme. Any requests containing the deprecated `X-Auth-Token` header will fail and receive an HTTP `401 Unauthorized` response.

**Before (v1):**
Authentication via custom token header:
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key_v1
```

**After (v2):**
Authentication via standard Bearer token:
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token_v2
```

---

### 3. Task ID Format Change
The task id format has changed. Specifically, the task `id` type changed from an auto-assigned integer to a standard UUID string format.
This change enables decentralized, offline task creation and avoids primary key conflicts across environments. Database schemas and client-side models must be updated from integer to string types to support this.

**Before (v1):**
Task objects used sequential integers for `id`:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2):**
Task objects use a UUID string representation for `id`:
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

### 4. Task Field Rename
The task field done has been renamed to completed.
To reflect task state more accurately, the boolean field `done` is no longer supported on the Task object. In v2, you must use the field name `completed` for both filtering, creating, updating, and parsing tasks.

**Before (v1):**
Task updates and retrieval used `done`:
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**
Task updates and retrieval must use `completed`:
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task Creation Requirements
Task creation now requires project_id. With the v2 release, the endpoint for creating tasks is now POST /v2/tasks, which requires the new project_id field.
In v1, you could create a task by providing only a `title`. In v2, creating a task requires associating it with a valid project. Omitting the `project_id` field in a `POST /v2/tasks` request will result in an HTTP `422 Unprocessable Entity` validation error.

**Before (v1):**
Task creation with only a title:
```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2):**
Task creation requiring both title and project_id:
```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Pagination Envelope
List endpoints return a paginated envelope instead of a bare array.
In v1, calling `GET /tasks` returned a flat JSON array of task objects. In v2, `GET /v2/tasks` returns a structured envelope object containing list metadata and an `items` array. This structure supports cursor-based pagination via the `?cursor=<next_cursor>` query parameter.

**Before (v1):**
Bare list response:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
Paginated envelope response:
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

---

## Migration Checklist

Please follow this step-by-step checklist to update your client integration from the Zrb Task API v1 to v2:

- [ ] **Scan and Audit Codebase**: Identify all files and network client code where `/tasks` endpoints are referenced.
- [ ] **Prefix Endpoints**: Update all request paths to include the `/v2/` prefix (e.g. change `/tasks` to `/v2/tasks`).
- [ ] **Update Auth Headers**: Replace all occurrences of the custom `X-Auth-Token` header with standard `Authorization: Bearer <your_api_token>` headers.
- [ ] **Update Client Model Types**: Update database schema structures and code models to change the `id` field from integer to UUID string.
- [ ] **Rename Task State Fields**: Change occurrences of the `done` property on tasks to `completed` in your UI, backend models, and serialisation logic.
- [ ] **Update Task Insertion Logic**: Add a valid `project_id` field to the payload of all task creation requests.
- [ ] **Unwrap List Responses**: Refactor your list retrieval logic to parse the paginated list envelope. Access the list of tasks from the nested `items` array rather than expecting a flat array directly.
- [ ] **Configure Cursor-based Pagination**: Implement cursor handling if iterating over paginated tasks by using the `next_cursor` value returned in the response metadata.
- [ ] **Execute Verification Tests**: Run integration and regression tests to verify that your updated API clients function correctly with the v2 endpoints.

---

## Upgrading the CLI

To fully complete your migration and start leveraging the latest features in your terminal, update your Zrb CLI installation by running the upgrade command below:

```bash
pip install --upgrade zrb
```
