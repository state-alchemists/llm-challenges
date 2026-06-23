# Zrb CLI v1 to v2 Migration Guide

Zrb CLI v2 is here, bringing significant enhancements including support for projects, improved pagination, and a more secure authentication mechanism. This guide outlines the breaking changes from v1 and provides clear steps and examples to help you seamlessly migrate your applications to the new API.

## What's New & Why Upgrade?

Zrb CLI v2 introduces several key improvements:

*   **Projects:** Organize your tasks more effectively by associating them with projects.
*   **Improved Pagination:** List endpoints now provide cursor-based pagination for more efficient data retrieval, especially with large datasets.
*   **Stricter Authentication:** Enhanced security with standard Bearer token authentication.
*   **UUID Task IDs:** Task IDs are now universally unique identifiers, offering better scalability and collision avoidance.

Upgrading to v2 will allow you to leverage these new features and ensure your applications are on the most current and robust version of the Zrb API.

## Breaking Changes and Migration Steps

This section details every breaking change, providing before-and-after code examples for clarity.

### 1. Endpoint Path Prefix

All API endpoints are now prefixed with `/v2/`. This change ensures versioning consistency and allows for future API evolution.

**Before (v1):**
```
GET /tasks
POST /tasks
GET /tasks/{id}
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
```

**Migration:** Update all your API request paths to include the `/v2/` prefix.

### 2. Authentication Header

The authentication mechanism has been updated to use a standard Bearer token. The `X-Auth-Token` header is no longer supported.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

**Migration:** Change your API key header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`. Requests using the old header will receive an HTTP 401 Unauthorized response.

### 3. Task ID Type Change

Task `id`s have transitioned from integers to UUID strings. This provides greater flexibility and uniqueness.

**Before (v1) Task Object:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Migration:** Update your code to expect `id`s as UUID strings instead of integers when parsing task objects or constructing requests.

### 4. Task Field Renaming (`done` to `completed`)

The boolean field indicating a task's completion status has been renamed for clarity.

**Before (v1) Update Task Request:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) Update Task Request:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

**Migration:** Replace all occurrences of the `done` field with `completed` in your code, both when sending requests and processing responses.

### 5. Task Creation Requires `project_id`

All new tasks in v2 must be associated with a project. The `project_id` field is now mandatory during task creation.

**Before (v1) Create Task Request:**
```json
{
  "title": "New task title"
}
```

**After (v2) Create Task Request:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Migration:** When creating tasks, ensure you include a `project_id` in your request body. Omitting this field will result in an HTTP 422 Unprocessable Entity error.

### 6. List Endpoints Return Paginated Envelope

List endpoints (`GET /v2/tasks`) no longer return a bare array of items. Instead, they return a paginated envelope containing `items`, `total`, and `next_cursor`.

**Before (v1) List Tasks Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) List Tasks Response:**
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

**Migration:**
*   Adjust your code to expect and parse the paginated envelope response for list operations.
*   Access the actual task objects from the `items` array.
*   Implement pagination logic using the `next_cursor` to fetch subsequent pages (e.g., `GET /v2/tasks?cursor=<next_cursor>`).

## Migration Checklist

To ensure a smooth migration, follow these steps:

1.  [ ] **Update API Endpoints:** Change all `/tasks` paths to `/v2/tasks`.
2.  [ ] **Modify Authentication:** Switch from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3.  [ ] **Adjust Task ID Handling:** Update your code to parse and generate UUID strings for task `id`s.
4.  [ ] **Rename Task Completion Field:** Replace `done` with `completed` in all task-related requests and responses.
5.  [ ] **Add `project_id` to Task Creation:** Ensure all `POST /v2/tasks` requests include a valid `project_id`.
6.  [ ] **Update List Response Parsing:** Modify your code to handle the new paginated envelope structure for list endpoints, accessing items via the `items` array.
7.  [ ] **Implement Pagination (Optional but Recommended):** Utilize the `cursor` and `next_cursor` for efficient data retrieval in list operations.
8.  [ ] **Test Thoroughly:** Run your integration tests to ensure all API calls and data handling work correctly with v2.

## Upgrade Your Zrb CLI

To upgrade your Zrb CLI installation to the latest version, run:

```bash
pip install --upgrade zrb
```
