# Zrb CLI Migration Guide from v1 to v2

## Introduction
This guide provides an overview of the breaking changes between v1 and v2 of the Zrb Task API and includes steps for migrating your applications and scripts to the new version.

## Breaking Changes

### 1. Endpoint Prefix Change
- **v1:** `/tasks`
- **v2:** `/v2/tasks`

#### Example: Fetching Tasks
**Before (v1):**
```http
GET /tasks
```
**After (v2):**
```http
GET /v2/tasks
```

### 2. Authentication Header Change
The authentication method has changed from `X-Auth-Token` to a Bearer token.

- **v1 Header:**
```http
X-Auth-Token: <your_api_key>
```
- **v2 Header:**
```http
Authorization: Bearer <your_api_token>
```

**Response to old header:** HTTP 401 Unauthorized

### 3. Task ID Type Change
The `id` field has changed from an integer to a UUID string.

#### Example: Task Object
**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```
**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 4. Field Rename
The field `done` in the Task object has been renamed to `completed`.

#### Example: Updating a Task
**Before (v1):**
```json
{
  "title": "Updated title",
  "done": true
}
```
**After (v2):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Required `project_id` Field
Creating a task now requires a `project_id` field.

#### Example: Creating a Task
**Before (v1):**
```json
{
  "title": "New task title"
}
```
**After (v2):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated Responses
List endpoints now return a paginated envelope instead of a bare array.

#### Example: List Tasks Response
**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```
**After (v2):**
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update API endpoint URLs to include `/v2/`.
2. Change authentication header to use `Authorization: Bearer <your_api_token>`.
3. Update your software to handle UUID strings for task IDs.
4. Rename the `done` field to `completed` in your task update and creation requests.
5. Ensure all creation requests include `project_id`.
6. Handle paginated responses when fetching lists of tasks.
7. Test all changes in a staging environment before deploying to production.

## Upgrade Command
Run the following command to upgrade:
```bash
npm install zrb-cli@latest
```