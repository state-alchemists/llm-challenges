# Migration Guide for Zrb CLI: v1 to v2

## Introduction
This document outlines the migration steps and the breaking changes from version 1 (v1) to version 2 (v2) of the Zrb Task API. It includes examples and a step-by-step migration checklist to assist developers in transitioning smoothly.

## Breaking Changes Overview

1. **Endpoint Prefix:** All endpoints are now prefixed with `/v2/`.
2. **Authentication Header:** Changed from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. **Task ID Type:** The task `id` type has changed from an integer to a UUID string.
4. **Field Renaming:** The task field `done` has been renamed to `completed`.
5. **Project ID Requirement:** Task creation now requires the `project_id` field.
6. **List Response Format:** List endpoints now return a paginated envelope instead of a bare array.

## Detailed Changes

### 1. Endpoint Prefix Change
**v1:**
```
GET /tasks
```

**v2:**
```
GET /v2/tasks
```

### 2. Authentication Header Change
**v1:**
```
X-Auth-Token: <your_api_key>
```

**v2:**
```
Authorization: Bearer <your_api_token>
```

**Example Change:**
Before:
```javascript
fetch('/tasks', { headers: { 'X-Auth-Token': 'your_api_key' } });
```
After:
```javascript
fetch('/v2/tasks', { headers: { 'Authorization': 'Bearer your_api_token' } });
```

### 3. Task ID Type Change
**v1:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**v2:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 4. Field Renaming
**v1:**
```json
{
  "done": false
}
```

**v2:**
```json
{
  "completed": false
}
```

### 5. Project ID Requirement on Task Creation
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

### 6. New Paginated List Response Format
**v1 Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."}
]
```

**v2 Response:**
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update API endpoint URLs to include `/v2/`.
2. Change the authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Update any references to `id` from integer to UUID string in task objects.
4. Rename any instances of the `done` field to `completed` in task updates and responses.
5. Ensure that `project_id` is included when creating new tasks.
6. Modify code to handle the new paginated response structure for task lists.

## Upgrade Command
To upgrade to the latest version of Zrb, run the following command:
```
npm install -g zrb@latest
```

Ensure to test your application after applying these changes to verify compatibility with the new version.