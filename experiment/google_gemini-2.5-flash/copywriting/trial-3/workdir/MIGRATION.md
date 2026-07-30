# Zrb CLI v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb CLI v2 and provides the necessary steps and code examples to migrate your existing v1 implementations. Zrb v2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication.

## Breaking Change: API Endpoint Prefix

All Zrb API endpoints in v2 are now prefixed with `/v2/`. This ensures versioning and allows for future API evolution without impacting older clients.

### Before (v1)

```
GET /tasks
POST /tasks
PUT /tasks/{id}
```

### After (v2)

```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
```

## Breaking Change: Authentication Header

The authentication mechanism has been updated from a custom `X-Auth-Token` header to a standard Bearer token in the `Authorization` header. Requests using the old header will be rejected with an HTTP 401 Unauthorized status.

### Before (v1)

```http
X-Auth-Token: <your_api_key>
```

### After (v2)

```http
Authorization: Bearer <your_api_token>
```

## Breaking Change: Task ID Type

The `id` field for Task objects has changed from an integer to a UUID string. This change provides greater flexibility and uniqueness for task identifiers across different projects and systems.

### Before (v1) Task Object

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

### After (v2) Task Object

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

## Breaking Change: Task Field `done` Renamed to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed` for improved clarity and consistency.

### Before (v1) Update Task Request

```json
{
  "done": true
}
```

### After (v2) Update Task Request

```json
{
  "completed": true
}
```

## Breaking Change: Task Creation Requires `project_id`

In v2, tasks are associated with projects. Therefore, `project_id` is now a mandatory field when creating a new task. Omitting `project_id` will result in an HTTP 422 Unprocessable Entity error.

### Before (v1) Create Task Request

```json
{
  "title": "New task title"
}
```

### After (v2) Create Task Request

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

## Breaking Change: List Endpoints Return Paginated Envelope

All list endpoints (e.g., `GET /v2/tasks`) no longer return a bare array of task objects. Instead, they return a paginated envelope containing the items, total count, and a `next_cursor` for subsequent pages.

### Before (v1) List Tasks Response

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2) List Tasks Response

```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    // ... more task objects
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, you would include the `cursor` query parameter: `GET /v2/tasks?cursor=cursor_xyz`.

---

## Migration Checklist

To ensure a smooth migration to Zrb CLI v2, follow these steps:

1.  [ ] **Update CLI:** Upgrade your Zrb CLI installation to v2.
2.  [ ] **Endpoint Paths:** Prefix all API endpoint calls with `/v2/`.
3.  [ ] **Authentication:** Change your `X-Auth-Token` header to `Authorization: Bearer <your_api_token>`.
4.  [ ] **Task IDs:** Update any code that handles Task IDs to expect UUID strings instead of integers.
5.  [ ] **Task Completion Field:** Rename all references to the `done` field to `completed`.
6.  [ ] **Task Creation:** Ensure all `POST /v2/tasks` requests include a `project_id` in the request body.
7.  [ ] **List Responses:** Adjust code that processes list endpoint responses to handle the new paginated envelope structure.
8.  [ ] **Pagination Logic:** Implement or update pagination logic using the `cursor` query parameter for list endpoints.

## Upgrade Command

To upgrade your Zrb CLI to v2, run the following command:

```bash
zrb upgrade --version v2
```
