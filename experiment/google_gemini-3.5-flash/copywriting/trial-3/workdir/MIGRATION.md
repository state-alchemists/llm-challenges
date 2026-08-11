# Zrb CLI v1 to v2 Migration Guide

Welcome to the Zrb CLI v2 Migration Guide. This document provides a detailed walkthrough of the breaking changes introduced in Zrb CLI v2, along with practical before-and-after examples to assist experienced developers in migrating their integrations seamlessly from v1 to v2.

The v2 release of the Zrb Task API introduces several key improvements, including projects association, cursor-based pagination, and stronger security standards. To adopt these improvements, you must update your API endpoints, authentication mechanisms, schemas, and payload structures.

---

## Breaking Changes

Below is a detailed breakdown of every breaking change between v1 and v2, including the technical rationale and corresponding code changes.

### 1. Endpoint Prefix Change (`/v2/`) and Required Project Association

In v2, all API endpoints are now prefixed with **/v2** to prevent namespace conflicts, and task creation now strictly requires a **project_id** association.

In the v1 API, tasks were managed under the root `/tasks` namespace, and tasks existed independently without project scoping. In v2, all endpoints are prefixed with `/v2/` (e.g., `GET /v2/tasks`), and every task must belong to a project. Creating a task without a `project_id` in the request payload will fail with an HTTP `422 Unprocessable Entity` status code.

**Before (v1 API - Task Creation):**
```http
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2 API - Task Creation):**
```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 2. Authentication Header Change (Bearer Token)

The custom authentication header has been replaced with standard HTTP Bearer token authentication. Requests using the legacy header will now receive an HTTP `401 Unauthorized` response.

To migrate, you must change your request headers to use the **Authorization** header with a **Bearer** token. Legacy requests using `X-Auth-Token` are no longer supported.

**Before (v1 API - Authentication Header):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2 API - Authentication Header):**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change (UUID String)

The data type of the task identifier `id` has been changed. In the v1 API, the `id` field was represented as an auto-assigned integer. In the v2 API, the identifier is represented as a **UUID** string.

This affects all path parameters and client-side models that deserialize the `id` field. For example, endpoints like `GET /v2/tasks/{id}`, `PUT /v2/tasks/{id}`, and `DELETE /v2/tasks/{id}` now expect a 36-character UUID string.

**Before (v1 API - Integer ID):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 API - UUID ID):**
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

To align with industry standard naming, the task schema has renamed the field representing completion status. The boolean field **done** from v1 is now renamed to **completed** in v2.

Ensure that your client deserializers, serializers, UI bindings, and update payloads are updated to use **completed** instead of **done**. Update requests (using `PUT`) that pass `done` will not affect the completion state.

**Before (v1 API - Update Task):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 API - Update Task):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. List Response Envelope (Pagination)

In the v1 API, the list tasks endpoint returned a bare JSON array. In the v2 API, the list response returns a paginated envelope to support large datasets efficiently.

The new response format wraps the array of tasks inside an `items` property. It also includes `total` (representing total records matching the query) and `next_cursor` (representing the cursor string for the next page) properties. You can fetch successive pages of results by appending `?cursor=<next_cursor>` to your request query parameters, with an optional custom page size via `&limit=<number>`.

**Before (v1 API - List Response):**
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

**After (v2 API - List Response):**
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

To successfully transition your application from Zrb v1 to v2, follow this step-by-step migration checklist:

- [ ] **Update Endpoint URIs**: Prepend `/v2` to all task-related endpoints in your application's API client.
- [ ] **Revise Authentication Headers**: Replace instances of `X-Auth-Token: <api_key>` with `Authorization: Bearer <token>` in your request configuration.
- [ ] **Refactor ID Data Types**: Update client-side data models and database schemas where task IDs are used, changing the data type from integer to a UUID string.
- [ ] **Update Task Property References**: Rename the `done` boolean field to `completed` across client serialization/deserialization logic, model attributes, and user interfaces.
- [ ] **Adopt Required Fields**: Update all task creation flows to retrieve a valid `project_id` and include it in the `POST /v2/tasks` request body.
- [ ] **Implement Pagination Support**: Refactor list page processing to expect the paginated response envelope structure (`items`, `total`, `next_cursor`) and handle cursor-based iteration.
- [ ] **Deploy and Verify**: Run tests, check for runtime errors, and verify with standard task management flows.

---

## Upgrade Command

Once you have completed all code modifications and updated your integration clients, upgrade your local Zrb installation to v2 using your preferred package manager.

To upgrade Zrb CLI globally using `pipx` (recommended):

```bash
pipx upgrade zrb
```

Alternatively, to upgrade using `pip` in your virtual environment:

```bash
pip install --upgrade zrb
```

For projects utilizing `poetry` for dependency management, update the package using:

```bash
poetry update zrb
```
