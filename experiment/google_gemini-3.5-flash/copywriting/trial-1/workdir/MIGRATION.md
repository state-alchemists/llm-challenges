# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI v2 and provides a step-by-step migration path to upgrade your existing v1 integrations to v2. The new version introduces projects, standardizes authentication, adopts UUIDs, and enhances listing APIs with a robust paginated response structure.

Experienced developers already using v1 should review every breaking change, update their API clients, modify database schemas, and follow the step-by-step checklist at the end of this guide.

---

## Architectural Improvements

Version 2 represents a major overhaul of our task management model. By introducing standard projects, Zrb now allows teams to partition tasks cleanly. To support high-scale deployments, offline task creation, and standard API practices, we have upgraded key data types, standardized endpoint naming schemes, and established secure session patterns.

---

## Breaking Changes

### 1. Endpoint Prefixing to `/v2/`
All endpoints in v2 are now prefixed with `/v2/` to support clean routing, side-by-side versioning, and to prevent future route collisions.

Ensure you update all client configurations to use the updated `/v2/` URL paths.

**Before (v1 API Endpoint Paths):**
```http
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2 API Endpoint Paths):**
```http
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authorization Bearer Authentication Header
The authentication mechanism has been updated to use standard HTTP Bearer token credentials via the `Authorization` header, completely replacing the custom `X-Auth-Token` header.

Requests using standard headers containing the legacy token will receive an HTTP 401 Unauthorized response from v2 servers.

**Before (v1 Custom Header):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2 Standard Header):**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Changed to UUID
To enable robust and unique ID generation across distributed offline environments, the Task `id` field has migrated from a sequential integer to a standard UUID string format.

Ensure your internal database schemas, primary/foreign key mappings, and parsing logic are updated to support UUID strings.

**Before (v1 Task Schema):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 Task Schema):**
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

### 4. Field Renamed from `done` to `completed`
To adopt cleaner, more descriptive and standardized terminology across Zrb platforms, the boolean field `done` is renamed to `completed`.

All references to `done` in filters, requests, and payloads must be renamed.

**Before (v1 Update Task Payload):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 Update Task Payload):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required `project_id` on Task Creation
Tasks are now scoped under projects. Therefore, the `project_id` field is **required** when calling the `/v2/` task creation endpoint.

Requests missing `project_id` will fail with an HTTP 422 Unprocessable Entity error.

**Before (v1 Task Creation):**
```http
POST /tasks
Content-Type: application/json
X-Auth-Token: 12345

{
  "title": "New task title"
}
```

**After (v2 Task Creation):**
```http
POST /v2/tasks
Content-Type: application/json
Authorization: Bearer 12345

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Envelope response instead of Bare Array
The listing API `GET /v2/tasks` now returns a paginated metadata envelope rather than a bare JSON array.

Clients must extract tasks from the `"items"` array of the envelope and handle pagination cursor parameters.

**Before (v1 Listing Response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 Listing Response):**
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

## Step-by-Step Migration Checklist

Follow these steps to migrate your integration from v1 to v2:

- [ ] **Step 1:** Run the CLI upgrade command to install the latest version of Zrb CLI.
- [ ] **Step 2:** Update your databases, schemas, models, and type definitions to support UUID keys for Task IDs instead of integers.
- [ ] **Step 3:** Rename any database columns, object properties, or serialization schemas from `done` to `completed`.
- [ ] **Step 4:** Ensure your applications supply a valid `project_id` string when creating tasks.
- [ ] **Step 5:** Modify API clients to prefix all Zrb requests with `/v2/`.
- [ ] **Step 6:** Replace standard headers that pass legacy tokens (`X-Auth-Token`) with `Authorization: Bearer <your_api_token>`.
- [ ] **Step 7:** Re-route your task list parsers to extract lists of task records from the `items` list of the new paginated envelope structure instead of parsing a bare JSON list.
- [ ] **Step 8:** Run a complete integration regression test suite and verify that no client encounters HTTP 401, 404, or 422 codes.

---

## Upgrade Command

To upgrade the Zrb CLI tool to the latest v2 version, run the following command in your terminal:

```bash
pip install --upgrade zrb
```
