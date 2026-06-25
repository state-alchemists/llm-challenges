# Zrb CLI v1 to v2 Migration Guide

Zrb CLI v2 introduces significant enhancements, including project management, improved pagination, and a more robust authentication mechanism. This guide outlines the breaking changes from v1 to v2 and provides a clear path for migration, ensuring a smooth transition for your existing integrations.

The v2 API emphasizes consistency and scalability, requiring updates to your code to leverage the new features and maintain compatibility.

## Breaking Changes

This section details every breaking change, providing before and after code examples to illustrate the necessary modifications.

### 1. All Endpoints are now prefixed with `/v2/`

All API endpoints have been updated to include a `/v2/` prefix, standardizing versioning across the API.

**Before (v1):**
```
GET /tasks
```

**After (v2):**
```
GET /v2/tasks
```

This change applies to all API endpoints: `/tasks`, `/tasks/{id}`.

### 2. Authentication Header Changed

The authentication method has been updated from a custom `X-Auth-Token` header to a standard Bearer token in the `Authorization` header. Requests using `X-Auth-Token` will now result in an HTTP 401 Unauthorized error.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task `id` Type Changed from Integer to UUID String

The `id` field for Task objects, used in both API payloads and URL paths, has transitioned from an integer to a UUID (Universally Unique Identifier) string. This provides greater uniqueness and prevents potential collisions.

**Before (v1 API Call):**
```
GET /tasks/42
```

**After (v2 API Call):**
```
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Before (v1 Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2 Task Object):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating the completion status of a task has been renamed from `done` to `completed` for improved clarity and consistency. This affects any API requests where this field is sent or received.

**Before (v1 Update Task Request Body):**
```json
{
  "done": true
}
```

**After (v2 Update Task Request Body):**
```json
{
  "completed": true
}
```

### 5. Task Creation Now Requires `project_id`

To support the new project management features, creating a new task now requires the `project_id` field in the request body. Omitting this field will result in an HTTP 422 Unprocessable Entity error.

**Before (v1 Create Task Request Body):**
```json
{
  "title": "New task title"
}
```

**After (v2 Create Task Request Body):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. List Endpoints Return a Paginated Envelope

All list-based endpoints (e.g., `GET /v2/tasks`) now return a standardized paginated envelope object instead of a bare array of items. This new structure includes metadata for pagination.

**Before (v1 List Tasks Response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 List Tasks Response):**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "project_id": "...", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, use the `next_cursor` value as a query parameter in subsequent requests:

**After (v2 List Tasks Request with Pagination):**
```
GET /v2/tasks?limit=50&cursor=cursor_xyz
```

## Migration Checklist

Follow these steps to migrate your Zrb CLI v1 integrations to v2:

1.  **Update API Endpoint Paths:** Modify all your API calls to include the `/v2/` prefix (e.g., `/tasks` becomes `/v2/tasks`).
2.  **Change Authentication Header:** Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>` in all authenticated requests.
3.  **Adjust Task ID Handling:** Update your code to expect and work with UUID strings for Task `id`s instead of integers.
4.  **Rename Task Field:** Change all references to the `done` field to `completed` in your Task object models and API request bodies.
5.  **Add `project_id` to Task Creation:** Ensure that every task creation request includes the new `project_id` field in its body.
6.  **Parse Paginated Responses:** Modify your code that consumes list endpoint responses to parse the new paginated envelope structure, accessing task data via the `items` array and handling `total` and `next_cursor` for pagination.

## Upgrade Command

To upgrade your Zrb CLI installation to v2, run the following command:

```bash
pip install --upgrade zrb
```
