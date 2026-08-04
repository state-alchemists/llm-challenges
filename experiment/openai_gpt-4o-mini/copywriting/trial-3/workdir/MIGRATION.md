# Zrb CLI Migration Guide from v1 to v2

This migration guide details the breaking changes between version 1 (v1) and version 2 (v2) of the Zrb CLI API. It provides guidelines for a smooth transition for developers already using v1. Following this guide will ensure your code continues to function correctly with the new API standards.

## Breaking Changes Overview

1. **Endpoint Prefix Change**: All endpoints are now prefixed with `/v2/`.
2. **Authentication Header Change**: The authentication method has been changed to a Bearer token.
3. **Task ID Type Change**: The `id` type for tasks has changed from an integer to a UUID string.
4. **Field Renaming**: The field `done` has been renamed to `completed`.
5. **Project ID Requirement**: Creating a task now requires a `project_id`.
6. **Paginated Responses**: List endpoints now return a paginated envelope instead of a bare array.

## Authentication

### Old Version (v1)
All requests require an API key passed in the header:

```http
X-Auth-Token: <your_api_key>
```

### New Version (v2)
Now requires a Bearer token:

```http
Authorization: Bearer <your_api_token>
```

### Code Examples

#### Before
```http
X-Auth-Token: abc123
```

#### After
```http
Authorization: Bearer abc123
```

## Data Types

### Task Object

#### Old Version (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### New Version (v2)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

## Endpoints

### List Tasks

#### Old Version (v1)

```http
GET /tasks
```
Returns a bare array of task objects:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

#### New Version (v2)

```http
GET /v2/tasks
```

**Query parameters:**
- `cursor` — pagination cursor (optional)
- `limit` — max results per page, default 20

Returns a paginated envelope:
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

### Create Task

#### Old Version (v1)

```http
POST /tasks
```
**Request body:**
```json
{
  "title": "New task title"
}
```

**Response:** the created task object (HTTP 201).

#### New Version (v2)

```http
POST /v2/tasks
```
**Request body:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

`project_id` is now **required**. Omitting it returns HTTP 422.

### Update Task

#### Old Version (v1)

```http
PUT /tasks/{id}
```
**Request body:**
```json
{
  "title": "Updated title",
  "done": true
}
```

#### New Version (v2)

```http
PUT /v2/tasks/{id}
```
**Request body:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### Delete Task

No changes here, remains the same in both versions.

## Migration Checklist

1. Update endpoint URLs to include `/v2/`.
2. Change authentication method to Bearer token in headers.
3. Update your task creation logic to include `project_id`.
4. Rename the `done` field to `completed` in task updates.
5. Change the `id` field type from integer to UUID string wherever applicable.
6. Ensure to handle paginated responses for listing tasks.

## Upgrade Command

Run the following command to upgrade:
```bash
yarn upgrade zrb-cli@latest
```

This guide provides all necessary changes for migrating from v1 to v2 of the Zrb CLI. For any questions or issues, please refer to the official documentation or reach out to the community.