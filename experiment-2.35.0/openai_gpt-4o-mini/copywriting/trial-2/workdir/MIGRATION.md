# Zrb CLI Migration Guide from v1 to v2

## Overview
This migration guide outlines the breaking changes between the Zrb CLI v1 and v2 and provides developers with code examples to assist in adapting to the new API specifications.

## Breaking Changes
The following changes have been made from v1 to v2:

### 1. Endpoint Prefix Change
All endpoints have been updated to include a version prefix.

**Before:**
```
GET /tasks
```
**After:**
```
GET /v2/tasks
```

---

### 2. Authentication Header Change
The method of authentication has changed from an API key in the header to a Bearer token.

**Before:**
```
X-Auth-Token: <your_api_key>
```
**After:**
```
Authorization: Bearer <your_api_token>
```
Requests using `X-Auth-Token` will receive an HTTP 401 response.

---

### 3. Task ID Type Change
The `id` field type for Task objects has changed from an integer to a UUID string.

**Before:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```
**After:**
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

### 4. Task Field Renaming
The `done` field has been renamed to `completed`.

**Before:**
```json
{
  "title": "Write test",
  "done": false
}
```
**After:**
```json
{
  "title": "Write test",
  "completed": false
}
```

---

### 5. New Required Field in Task Creation
Creating a task now requires the `project_id` field, which was not required in v1.

**Before:**
```json
{
  "title": "New task title"
}
```
**After:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```
Omitting `project_id` will return HTTP 422.

---

### 6. Pagination Added to List Endpoints
List endpoints now return a paginated envelope instead of a bare array. You will need to handle the pagination cursor.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```
**After:**
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
To fetch the next page, include `?cursor=<next_cursor>` in your request.

## Migration Steps
To facilitate a smooth transition to v2, follow the checklist below:
1. Update all API endpoints from `/tasks` to `/v2/tasks`.
2. Change the authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Modify your task data handling to use UUIDs for the `id` field.
4. Rename instances of the `done` field to `completed` in your task objects.
5. Ensure that the `project_id` field is included when creating tasks.
6. Update any logic that handles task lists to accommodate the new paginated response structure.

## Upgrade Command
To upgrade to the latest version of Zrb CLI, run:
```
npm install -g zrb
```

Ensure to test all your changes thoroughly. If you encounter issues, consult the Zrb documentation or community for assistance.