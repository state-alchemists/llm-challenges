# Zrb CLI v2 Migration Guide

Zrb CLI v2 introduces several significant improvements, including project support, enhanced pagination, and a more secure authentication mechanism. This guide will walk experienced v1 users through the breaking changes and provide a step-by-step migration path.

## Breaking Changes Summary

The following are the key breaking changes introduced in Zrb CLI v2:

1.  **Endpoint Prefix**: All API endpoints are now prefixed with `/v2/`.
2.  **Authentication Header**: The `X-Auth-Token` header has been replaced with a standard `Authorization: Bearer` token.
3.  **Task ID Type**: Task IDs have changed from integers to UUID strings.
4.  **Task Field Renamed**: The `done` field on Task objects has been renamed to `completed`.
5.  **Task Creation Requirement**: Creating a task now requires a `project_id`.
6.  **Paginated List Responses**: List endpoints now return a paginated envelope object instead of a bare array of items.

## Detailed Breaking Changes and Migration Steps

### 1. Endpoint Prefix Change

All API endpoints in v2 are now prefixed with `/v2/`. This applies to all task-related operations.

**Before (v1):**
```bash
curl -X GET "https://api.zrb.com/tasks" \
     -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**
```bash
curl -X GET "https://api.zrb.com/v2/tasks" \
     -H "Authorization: Bearer <your_api_token>"
```

**Migration:** Update all your API request paths to include the `/v2/` prefix.

### 2. Authentication Header Change

The authentication mechanism has been updated for improved security and standardization.

**Before (v1):**
```bash
curl ... \
     -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**
```bash
curl ... \
     -H "Authorization: Bearer <your_api_token>"
```

**Migration:** Replace all instances of `X-Auth-Token` with `Authorization: Bearer` in your request headers. Ensure you use your new v2 API token. Requests with the old header will receive an HTTP 401 Unauthorized response.

### 3. Task ID Type Change

Task IDs are no longer simple integers; they are now UUID strings. This affects all endpoints that take an ID as a path parameter.

**Before (v1) - Task Object:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "..."
}
```

**Before (v1) - Get Task:**
```bash
curl -X GET "https://api.zrb.com/tasks/42" \
     -H "X-Auth-Token: <your_api_key>"
```

**After (v2) - Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "..."
}
```

**After (v2) - Get Task:**
```bash
curl -X GET "https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
     -H "Authorization: Bearer <your_api_token>"
```

**Migration:** Update your code to handle UUID strings for task IDs. This means changing any integer parsing or generation logic for task IDs.

### 4. Task Field Renamed: `done` to `completed`

The boolean field indicating a task's completion status has been renamed for clarity.

**Before (v1) - Update Task:**
```bash
curl -X PUT "https://api.zrb.com/tasks/42" \
     -H "X-Auth-Token: <your_api_key>" \
     -H "Content-Type: application/json" \
     -d '{"done": true}'
```

**After (v2) - Update Task:**
```bash
curl -X PUT "https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
     -H "Authorization: Bearer <your_api_token>" \
     -H "Content-Type: application/json" \
     -d '{"completed": true}'
```

**Migration:** Rename all references to the `done` field to `completed` in your Task object parsing and request bodies.

### 5. Task Creation Requires `project_id`

To align with the new project-centric structure, all new tasks must now be associated with a `project_id`.

**Before (v1) - Create Task:**
```bash
curl -X POST "https://api.zrb.com/tasks" \
     -H "X-Auth-Token: <your_api_key>" \
     -H "Content-Type: application/json" \
     -d '{"title": "New task title"}'
```

**After (v2) - Create Task:**
```bash
curl -X POST "https://api.zrb.com/v2/tasks" \
     -H "Authorization: Bearer <your_api_token>" \
     -H "Content-Type: application/json" \
     -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

**Migration:** When creating new tasks, ensure your request body includes the `project_id` field. Omitting this will result in an HTTP 422 Unprocessable Entity error.

### 6. Paginated List Responses

All list endpoints (e.g., `GET /v2/tasks`) now return a standardized paginated envelope object, rather than a direct array of items.

**Before (v1) - List Tasks Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) - List Tasks Response:**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Pagination Query Parameters (v2):**
```bash
# First page
curl -X GET "https://api.zrb.com/v2/tasks?limit=10" \
     -H "Authorization: Bearer <your_api_token>"

# Subsequent page
curl -X GET "https://api.zrb.com/v2/tasks?cursor=cursor_xyz&limit=10" \
     -H "Authorization: Bearer <your_api_token>"
```

**Migration:** Update your code to expect a paginated envelope object. Access the list of tasks via the `items` field. Implement pagination logic using the `next_cursor` field and the `cursor` query parameter for subsequent requests.

## Migration Checklist

To ensure a smooth migration to Zrb CLI v2, follow these steps:

1.  [ ] **Update Endpoint Paths**: Prefix all API endpoint URLs with `/v2/`.
2.  [ ] **Change Authentication Header**: Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>`.
3.  [ ] **Adjust Task ID Handling**: Update your code to parse and use UUID strings for task IDs instead of integers.
4.  [ ] **Rename `done` field**: Change all references from `done` to `completed` in task objects and request bodies.
5.  [ ] **Add `project_id` to Task Creation**: Include the `project_id` field when creating new tasks.
6.  [ ] **Adapt to Paginated Responses**: Modify list endpoint calls to read from the `items` array within the new paginated envelope and implement cursor-based pagination.
7.  [ ] **Test Thoroughly**: Run your application's test suite against the v2 API to catch any regressions.

## Upgrade Command

To upgrade your Zrb CLI installation to the latest v2 version, run:

```bash
zrb upgrade --version 2.x
```
Replace `2.x` with the specific version you wish to upgrade to, or omit `--version` for the latest stable v2 release.
