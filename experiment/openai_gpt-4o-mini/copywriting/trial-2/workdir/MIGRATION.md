# Zrb CLI Migration Guide: v1 to v2

## Introduction
This guide provides a detailed overview of the breaking changes in the Zrb CLI API from version 1 (v1) to version 2 (v2). It includes code examples for each change and a step-by-step migration checklist to facilitate the transition.

## Breaking Changes Summary
1. **Endpoint Prefix**: All endpoints are now prefixed with `/v2/`.
2. **Authentication Header**: Updated from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. **Task ID Type**: The `id` field type has changed from integer to UUID string.
4. **Field Renaming**: The `done` field is now `completed`.
5. **Task Creation Requirement**: The `project_id` field is now required for task creation.
6. **Paginated Response**: List endpoints return a paginated envelope instead of a bare array.

## Detailed Changes

### 1. Endpoint Prefix
**Before**:
```plaintext
GET /tasks
```
**After**:
```plaintext
GET /v2/tasks
```

### 2. Authentication Header
**Before**:
```plaintext
X-Auth-Token: <your_api_key>
```
**After**:
```plaintext
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
**Before** (v1):
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```
**After** (v2):
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
**Before**:
```json
{
  "title": "Updated title",
  "done": true
}
```
**After**:
```json
{
  "title": "Updated title",
  "completed": true
}
```

### 5. Task Creation Requirement
**Before**:
```json
{
  "title": "New task title"
}
```
**After**:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated Response
**Before** response:
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```
**After** response:
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
- [ ] Update all endpoint URLs to include the `/v2/` prefix.
- [ ] Change the authentication header to use Bearer tokens.
- [ ] Update task ID fields from integer to UUID strings.
- [ ] Rename the `done` field to `completed` in task objects.
- [ ] Add `project_id` as a required field in task creation requests.
- [ ] Modify the logic to handle paginated responses for list endpoints.

## Upgrade Command
Run the following command to upgrade to v2:
```bash
zrb upgrade
```