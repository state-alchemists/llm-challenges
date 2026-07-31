# Zrb Task API Migration Guide: v1 to v2

## Overview
This guide outlines the breaking changes when migrating from Zrb Task API v1 to v2. Please follow the examples closely to adjust your existing implementations.

## Breaking Changes

### 1. Endpoints Prefix
**Change**: All endpoints are now prefixed with `/v2/`

**Before**:
```http
GET /tasks
```
**After**:
```http
GET /v2/tasks
```

### 2. Authentication Header
**Change**: The authentication header has changed from `X-Auth-Token` to a Bearer token.

**Before**:
```http
X-Auth-Token: <your_api_key>
```
**After**:
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
**Change**: The `id` type has changed from an integer to a UUID string in the Task object.

**Before**:
```json
{"id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z"}
```
**After**:
```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
```

### 4. Task Field Rename
**Change**: The `done` field has been renamed to `completed`.

**Before**:
```json
{"done": false}
```
**After**:
```json
{"completed": false}
```

### 5. Required Project ID for Task Creation
**Change**: The creation of a Task now requires the `project_id` field.

**Before**:
```json
{"title": "New task title"}
```
**After**:
```json
{"title": "New task title", "project_id": "proj_abc123"}
```

### 6. Paginated List Response
**Change**: List endpoints now return a paginated envelope instead of a bare array.

**Before**:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```
**After**:
```json
{"items": [...], "total": 42, "next_cursor": "cursor_xyz"}
```

## Migration Checklist
1. Update all endpoint URLs to include the `/v2/` prefix.
2. Change from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Update all instances of `id` from integer to UUID string format.
4. Rename all `done` fields to `completed`.
5. Ensure that all Task creation requests include the `project_id`.
6. Adapt your list endpoint handling to work with a paginated envelope.

## Upgrade Command
To upgrade the Zrb CLI to version 2, use the following command:
```bash
zrb upgrade
```