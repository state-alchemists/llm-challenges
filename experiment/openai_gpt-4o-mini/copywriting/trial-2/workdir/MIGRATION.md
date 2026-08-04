# Zrb CLI Migration Guide: From v1 to v2

## Overview
This guide details the migration process from Zrb CLI v1 to v2, highlighting all breaking changes along with code examples to facilitate a smooth transition for experienced developers.

## Breaking Changes

### 1. Endpoint Prefix
**Change:** All API endpoints are now prefixed with `/v2/`.

**Before:**
```http
GET /tasks
```
**After:**
```http
GET /v2/tasks
```

### 2. Authentication Header Change
**Change:** The authentication method has changed from `X-Auth-Token` to a Bearer token.

**Before:**
```http
X-Auth-Token: <your_api_key>
```
**After:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
**Change:** Task IDs have changed from integer to UUID string.

**Before:**
```json
{"id": 1,"title": "Write tests", ...}
```
**After:**
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", ...}
```

### 4. Task Field Renaming
**Change:** The task field `done` has been renamed to `completed`.

**Before:**
```json
{"done": false}
```
**After:**
```json
{"completed": false}
```

### 5. Required Field Addition
**Change:** Task creation now requires the `project_id` field.

**Before:**
```json
{"title": "New task title"}
```
**After:**
```json
{"title": "New task title", "project_id": "proj_abc123"}
```

### 6. Pagination Changes
**Change:** List endpoints now return a paginated envelope instead of a bare array.

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
       {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false}
   ],
   "total": 1,
   "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update API endpoint URLs by adding `/v2/` prefix.
2. Change the authentication header to use Bearer token.
3. Update task IDs to UUID format.
4. Rename the `done` field to `completed` in task objects.
5. Ensure that the `project_id` field is included in task creation requests.
6. Modify the code to handle paginated responses from list endpoints.

## Upgrade Command
To update to v2, run:
```bash
npm install zrb-cli@latest
```