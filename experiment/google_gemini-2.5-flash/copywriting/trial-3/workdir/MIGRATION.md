# Zrb CLI v1 to v2 Migration Guide

This guide provides a comprehensive overview of the breaking changes introduced in Zrb CLI v2 and offers clear instructions for migrating your existing v1 integrations. Version 2 brings significant enhancements, including native support for projects, improved pagination, and stricter authentication, leading to a more robust and scalable API.

Our goal is to make your transition to v2 as smooth as possible.

## Breaking Changes and Migration Steps

The following sections detail each breaking change, providing a clear explanation and illustrating the necessary code modifications with before-and-after examples.

### 1. All Endpoints Now Use a `/v2/` Prefix

All API endpoints have been updated to include a `/v2/` prefix to clearly delineate between API versions and enable future extensibility.

**Before (v1):**
```
GET /tasks
POST /tasks
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
```

**Migration:** Update all API request paths to include the `/v2/` segment immediately after the base URL.

### 2. Authentication Header Changed

The authentication mechanism has been updated for improved security and standardization. The `X-Auth-Token` header is no longer supported. All requests must now use a standard `Authorization: Bearer` token.

**Before (v1):**
```
X-Auth-Token: <your_api_key>
```

**After (v2):**
```
Authorization: Bearer <your_api_token>
```

**Migration:** Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>` in your request headers. Requests using the old header will receive an HTTP 401 Unauthorized response.

### 3. Task `id` Type Changed from Integer to UUID String

Task identifiers are now globally unique UUID strings, offering better scalability and preventing potential ID collisions across systems.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

**Migration:** Update your code to expect and handle `task.id` as a string (UUID) instead of an integer. This impacts all operations that reference a task by its ID (e.g., Get Task, Update Task, Delete Task).

### 4. Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed for clarity and consistency.

**Before (v1):**
```json
{
  "title": "Updated title",
  "done": true
}
```
(Used in `PUT /tasks/{id}`)

**After (v2):**
```json
{
  "title": "Updated title",
  "completed": true
}
```
(Used in `PUT /v2/tasks/{id}`)

**Migration:** When creating or updating tasks, replace all references to the `done` field with `completed`.

### 5. Task Creation Now Requires `project_id`

Zrb CLI v2 introduces the concept of projects, and every new task must now be associated with a `project_id`.

**Before (v1):**
```json
{
  "title": "New task title"
}
```
(Used in `POST /tasks`)

**After (v2):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```
(Used in `POST /v2/tasks`)

**Migration:** Ensure that all `POST /v2/tasks` requests include a `project_id` in the request body. Omitting this field will result in an HTTP 422 Unprocessable Entity error.

### 6. List Endpoints Return a Paginated Envelope

To support efficient retrieval of large datasets, all list endpoints (e.g., `GET /v2/tasks`) now return results wrapped in a paginated envelope object, rather than a bare array.

**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```
(Response from `GET /tasks`)

**After (v2):**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_abc", "created_at": "..."},
    {"id": "uuid-2", "title": "Ship v2", "completed": true, "project_id": "proj_abc", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```
(Response from `GET /v2/tasks`)

**Migration:**
*   Access task data from the `items` array within the response envelope.
*   Implement pagination logic using the `next_cursor` field. To fetch the next page, append `?cursor=<next_cursor>` to your request.
*   The `GET /v2/tasks` endpoint also supports a `limit` query parameter (default: 20) to control the number of results per page.

## Migration Checklist

Follow these steps to successfully migrate your Zrb CLI v1 integrations to v2:

1.  [ ] **Update CLI:** Upgrade your Zrb CLI installation to v2.
2.  [ ] **Adjust Endpoint Paths:** Prefix all API endpoint URLs with `/v2/`.
3.  [ ] **Change Authentication:** Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>`.
4.  [ ] **Handle UUID IDs:** Update all code that processes task IDs to expect UUID strings instead of integers.
5.  [ ] **Rename `done` to `completed`:** Modify code to use the `completed` field for task status.
6.  [ ] **Add `project_id` to Task Creation:** Ensure `project_id` is included in the request body when creating new tasks.
7.  [ ] **Update List Endpoint Consumption:** Refactor code to parse list responses from the paginated envelope's `items` array and implement pagination using `next_cursor`.
8.  [ ] **Test Thoroughly:** Verify all migrated integrations against the new v2 API.

## Upgrade Command

To upgrade your Zrb CLI installation to version 2, run the following command:

```bash
zrb upgrade --to v2
```
