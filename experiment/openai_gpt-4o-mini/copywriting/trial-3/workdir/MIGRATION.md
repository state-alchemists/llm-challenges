# Zrb CLI Migration Guide from v1 to v2

This migration guide provides developers with the necessary information to transition from version 1 (v1) to version 2 (v2) of the Zrb CLI API. The new version introduces several breaking changes and improvements. Each breaking change is outlined below with examples and a checklist for migrating your existing code.

## Breaking Changes

### 1. Endpoint Prefix Change
All endpoints are now prefixed with `/v2/`.

**Before:**
```http
GET /tasks
```
**After:**
```http
GET /v2/tasks
```

### 2. Authentication Header Change
The authentication header has changed from `X-Auth-Token` to a Bearer token.

**Before:**
```http
X-Auth-Token: <your_api_key>
```
**After:**
```http
Authorization: Bearer <your_api_token>
```

**Note:** Requests using the old header will receive an HTTP 401 error.

### 3. Task ID Type Change
The `id` field for task objects is now a UUID string rather than an integer.

**Before:**
```json
{"id": 42}
```
**After:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}
```

### 4. Task Field Renaming: `done` to `completed`
The `done` field in task objects has been renamed to `completed`.

**Before:**
```json
{"done": false}
```
**After:**
```json
{"completed": false}
```

### 5. Required Project ID for Task Creation
Creating a new task now requires a `project_id` field in the request body.

**Before:**
```json
{"title": "New task title"}
```
**After:**
```json
{"title": "New task title", "project_id": "proj_abc123"}
```

Omitting `project_id` will return an HTTP 422 error.

### 6. Paginated List Envelope
List endpoints now return a paginated response instead of a bare array.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```
**After:**
```json
{
  "items": [
    {"id": "1", "title": "Buy milk", "completed": false},
    {"id": "2", "title": "Ship v1", "completed": true}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update all API URLs to include the `/v2/` prefix.
2. Change your authentication method:
   - Replace `X-Auth-Token` in headers with `Authorization: Bearer <your_api_token>`.
3. Review and adjust the task object to replace the integer `id` with a UUID string.
4. Rename all instances of the `done` field to `completed`.
5. Ensure all task creation requests include the `project_id` field.
6. Modify code to work with the new paginated response structure from list endpoints.

## Upgrade Command
To upgrade to the latest version of Zrb CLI, run the following command:
```bash
gem install zrb
```