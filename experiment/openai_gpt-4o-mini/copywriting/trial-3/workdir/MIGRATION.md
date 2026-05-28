# Zrb API Migration Guide from v1 to v2

## Introduction
This migration guide outlines the breaking changes between Zrb's version 1 (v1) and version 2 (v2) of the Task API. Users of v1 should follow the steps outlined below to successfully migrate their applications to v2.

## Breaking Changes

### 1. Endpoint Structure
**v1:**
```
GET /tasks
```
**v2:**
```
GET /v2/tasks
```

### 2. Authentication Header
**v1:**
```
X-Auth-Token: <your_api_key>
```

**v2:**
```
Authorization: Bearer <your_api_token>
```
Requests with the old header will result in HTTP 401 responses.

### 3. Task ID Type
**v1:**
```json
{
  "id": 42,
}
```
**v2:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
}
```
The `id` has changed from an integer to a UUID string.

### 4. Task Field Renaming
**v1:**
```json
{
  "done": false,
}
```

**v2:**
```json
{
  "completed": false,
}
```
The `done` field is now renamed to `completed`.

### 5. Required Field in Task Creation
**v1:**
```json
{
  "title": "New task title"
}
```

**v2:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```
The `project_id` field is now required in task creation. Omitting it will result in an HTTP 422 error.

### 6. Paginated List Responses
**v1:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**v2:**
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
All list endpoints return a paginated envelope instead of a bare array.

## Migration Checklist
1. Update endpoint URLs to use `/v2/` prefix.
2. Change authentication from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Modify task ID handling from integer to UUID string.
4. Update any instances of the `done` field to `completed`.
5. Ensure `project_id` is included in all task creation requests.
6. Implement pagination handling in list requests and modify the response handling to manage the new format.

## Upgrade Command
Run the following command to upgrade to the latest version:
```
npm install zrb@latest
```