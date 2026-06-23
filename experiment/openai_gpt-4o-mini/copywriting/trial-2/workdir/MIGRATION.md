# Zrb Migration Guide: v1 to v2

## Introduction
This guide outlines the breaking changes introduced in Zrb version 2 (v2) compared to version 1 (v1). It provides clear examples and a checklist to assist developers in migrating their code.

## Breaking Changes

### 1. Endpoints
All endpoints are now prefixed with `/v2/`.

**Before:**
```
GET /tasks
```
**After:**
```
GET /v2/tasks
```

### 2. Authentication Header
The authentication header has changed from `X-Auth-Token` to a Bearer token.

**Before:**
```
X-Auth-Token: <your_api_key>
```
**After:**
```
Authorization: Bearer <your_api_token>
```

Requests using the old token format will receive an HTTP 401 response.

### 3. Task `id` Type
The `id` field has changed from an integer to a UUID string format.

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

### 4. Task Field Renaming
The `done` field has been renamed to `completed`.

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

### 5. Required `project_id`
Creating a task now requires the `project_id` field, which was not previously required.

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

### 6. Paginated List Envelope
All list endpoints now return a paginated result instead of a bare array.

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

## Migration Checklist
1. Update all endpoint URLs to include `/v2/`.
2. Change the authentication header to bearer token format.
3. Update any references to `id` from integer to UUID string.
4. Rename all occurrences of `done` to `completed` in task objects.
5. Ensure that `project_id` is included in all task creation requests.
6. Modify code to handle paginated response envelopes instead of flat arrays.

## Upgrade Command
To upgrade to the latest version of Zrb CLI, run:
```
npm install -g zrb@latest
```