# Zrb CLI Migration Guide from v1 to v2

## Introduction
This migration guide details the breaking changes from Zrb CLI v1 to v2. Please follow the instructions and examples carefully to ensure a smooth transition.

## Breaking Changes

### 1. Endpoint Prefixes
All endpoints have been prefixed with `/v2/`.

**Before:**
```plaintext
GET /tasks
```
**After:**
```plaintext
GET /v2/tasks
```

### 2. Authentication Header Change
The authentication header has changed from `X-Auth-Token` to Bearer token.

**Before:**
```plaintext
X-Auth-Token: <your_api_key>
```
**After:**
```plaintext
Authorization: Bearer <your_api_token>
```
Requests with the old header will receive HTTP 401.

### 3. Task `id` Type Change
The `id` of the task object has changed from an integer to a UUID string.

**Before:**
```json
{
  "id": 42,
  "title": "Write tests"
}
```
**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. `done` Field Renamed to `completed`
The field `done` is now renamed to `completed` in the task object.

**Before:**
```json
{
  "done": false
}
```
**After:**
```json
{
  "completed": false
}
```

### 5. Required `project_id` for Task Creation
Task creation now requires a `project_id`, which is a new field. If omitted, it returns HTTP 422.

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

### 6. Paginated List Responses
List endpoints now return a paginated envelope instead of a bare array of tasks. 

**Before:**
```json
[
  {"id": 1, "title": "Buy milk"},
  {"id": 2, "title": "Ship v1"}
]
```
**After:**
```json
{
  "items": [{"id": 1, "title": "Buy milk"}, {"id": 2, "title": "Ship v1"}],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update endpoint URLs to prepend `/v2/`.
2. Change the authentication header to use Bearer token.
3. Update task `id` handling to treat it as a UUID string.
4. Rename `done` fields to `completed` in your application logic.
5. Ensure `project_id` is included in all task creation requests.
6. Modify list endpoint responses to handle paginated outputs.

## Upgrade Command
To upgrade Zrb CLI, run:
```bash
pip install --upgrade zrb
```