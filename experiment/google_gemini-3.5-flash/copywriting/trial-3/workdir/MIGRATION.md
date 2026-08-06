# Zrb CLI v2 Migration Guide

Zrb v2 introduces significant architectural upgrades to improve scalability, security, and developer ergonomics. This version introduces multi-project partitioning, cursor-based pagination, and standard token-based authentication. However, these improvements introduce several breaking changes that are incompatible with v1.

This document serves as a comprehensive migration guide for experienced developers who are currently integrating with v1. It details each breaking change, displays before/after comparison examples, provides a step-by-step checklist, and concludes with the upgrade instructions.

---

## Major Breaking Changes

### 1. Endpoint Path Prefixing (`/v2` Namespace)

All endpoints are now prefixed with `/v2/` to support multi-version routing and ensure future extensibility. Any client request addressing the legacy root paths without the `/v2` namespace will fail.

**Before (v1 API Paths):**
```http
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2 API Paths):**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Bearer Token Authentication

The authentication mechanism has transitioned from a custom header to a standard Bearer authentication scheme. For authentication, clients must now provide an **Authorization** header containing a **Bearer** token. Sending requests with the legacy `X-Auth-Token` header will return an HTTP 401 Unauthorized error.

**Before (v1 Authentication Header):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2 Authentication Header):**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task Identifier Format (Integer to UUID)

To support decentralized generation and prevent identifier enumeration attacks, task IDs have been migrated. In v2, the task `id` is a 36-character **UUID** string rather than a sequential integer. You must alter database schemas, JSON schemas, and routing parameter types in your codebase to accept string-based UUID values.

**Before (v1 Task ID Format):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 Task ID Format):**
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

### 4. Completion Status Field Rename (`done` to `completed`)

To achieve better alignment with industry conventions, the completion state field has been renamed. The task completion field has been renamed from **done** to **completed** across all models. Serialization logic, boolean checks, and local classes must be updated to reference the new field name.

**Before (v1 Field Name):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 Field Name):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required Project Association (`project_id`)

All tasks in v2 must be created within the scope of a specific project. Task creation requests under the **/v2** prefix namespace now require a **project_id** field. If a payload is sent to `POST /v2/tasks` without this attribute, the API will reject it with an HTTP 422 Unprocessable Entity error.

**Before (v1 Creation Payload):**
```json
{
  "title": "New task title"
}
```

**After (v2 Creation Payload):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Response Envelope

To prevent high latency on repositories with large task volumes, list requests no longer yield a raw, unpaginated JSON array. Instead, they return a structured, paginated envelope containing list metadata alongside an array of items. Developers must update list handling logic to unpack results from the `items` key.

**Before (v1 List Payload):**
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

**After (v2 List Payload):**
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

Follow these steps sequentially to transition your codebase from Zrb v1 to v2:

- [ ] **Base API Paths**: Update all request endpoints to utilize the new `/v2/` prefix.
- [ ] **Authentication**: Replace headers containing `X-Auth-Token` with the new Bearer format: `Authorization: Bearer <token>`.
- [ ] **Data Model (IDs)**: Alter your database tables and application models to support task IDs as 36-character UUID strings instead of sequential integers.
- [ ] **Data Model (Fields)**: Rename references to the task status field from `done` to `completed` in both request payloads and response readers.
- [ ] **Task Creation**: Update all creation calls (`POST /v2/tasks`) to supply a valid `project_id`.
- [ ] **Pagination Parsers**: Refactor code consuming lists (`GET /v2/tasks`) to extract the list items from the `items` key of the response envelope, and optionally leverage `next_cursor` for paginated retrieval.
- [ ] **Testing**: Run integration tests to verify successful end-to-end communication with the v2 service.

---

## How to Upgrade

Once your codebase is fully compliant with the Zrb v2 specification, you can upgrade your local CLI installation using the standard pip package manager:

```bash
pip install --upgrade zrb
```
