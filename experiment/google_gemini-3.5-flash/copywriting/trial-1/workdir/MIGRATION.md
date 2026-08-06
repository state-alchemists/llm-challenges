# Zrb CLI v1 to v2 Migration Guide

Welcome to the Zrb CLI v2 Migration Guide. This document provides step-by-step instructions for upgrading your applications and integrations from Zrb v1 to Zrb v2.

Zrb v2 introduces support for projects, improved cursor-based pagination, and stricter security protocols. To support these features, several breaking changes have been introduced to the API. This guide walks you through every breaking change with before/after comparison examples, provides a migration checklist, and ends with the CLI upgrade command.

---

## Breaking Changes

### 1. Global Endpoint API Version Prefixing
All API endpoints in v2 are now versioned. Previously, endpoints were located at the root of the path. Under the new `/v2/` endpoint, creating a task now requires a project_id.

#### Before (v1):
```http
GET /tasks
POST /tasks
GET /tasks/{id}
```

#### After (v2):
```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
```

---

### 2. Authentication Header Change (X-Auth-Token to Bearer)
Authentication has been updated to follow standard OAuth2 practices. The authentication now uses Bearer token in the Authorization header. Passing the old header will result in an HTTP `401 Unauthorized` response.

#### Before (v1):
```http
X-Auth-Token: <your_api_key>
```

#### After (v2):
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change (Integer to UUID)
To support distributed generation and prevent ID enumeration, the task ID type has changed from integer to UUID string. If your system stores these IDs as integers, you must migrate your schema to support strings (specifically 36-character UUIDv4 strings).

#### Before (v1 Task Object):
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2 Task Object):
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

### 4. Task Completed Field Rename
The task field done has been renamed to completed in v2. Any logic or UI components relying on `done` must be updated to use the new `completed` boolean property.

#### Before (v1 Update/Task Response):
```json
{
  "done": true
}
```

#### After (v2 Update/Task Response):
```json
{
  "completed": true
}
```

---

### 5. Task Creation project_id Constraint
Creating a task now requires an associated project. When posting to the creation endpoint, you must supply a valid `project_id` string. Omitting this field will result in an HTTP `422 Unprocessable Entity` validation error.

#### Before (v1 Request Body):
```json
{
  "title": "New task title"
}
```

#### After (v2 Request Body):
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Endpoint Pagination Envelope
List endpoints no longer return a bare JSON array. In v2, list endpoints return a paginated envelope object with `items`, `total`, and `next_cursor` attributes to support efficient cursor-based navigation.

#### Before (v1 GET /tasks Response):
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

#### After (v2 GET /v2/tasks Response):
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

To fetch subsequent pages, pass the returned `next_cursor` as a query parameter:
```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your code from Zrb v1 to v2:

- [ ] **Update API Endpoint Base Paths**: Change all URL paths from `/{endpoint}` to `/v2/{endpoint}`.
- [ ] **Update Auth Headers**: Replace the `X-Auth-Token: <api_key>` header with `Authorization: Bearer <token>` in all API requests.
- [ ] **Migrate Database IDs**: Modify local database tables and models where task IDs are stored to use UUID strings instead of integers.
- [ ] **Rename Status Fields**: Update serialisation/deserialisation schemas and frontend models to map `done` to `completed`.
- [ ] **Inject project_id into Creation Calls**: Identify the project context in your application and ensure `project_id` is passed during task creation.
- [ ] **Parse Paginated Envelopes**: Update listing page logic to read from `response.items` rather than processing the top-level array directly, and integrate cursor-based pagination.
- [ ] **Perform Integration Testing**: Test all task CRUD flows against the new v2 endpoints.

---

## Upgrade to v2

Once you have completed code migration, you can upgrade your Zrb CLI package. Run the following command in your terminal to install the latest version of Zrb:

```bash
pip install --upgrade zrb
```
