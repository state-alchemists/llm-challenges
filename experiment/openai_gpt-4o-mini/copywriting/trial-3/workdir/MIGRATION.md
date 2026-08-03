# Zrb Task API Migration Guide: v1 to v2

## Overview
This guide details the migration process from Zrb API v1 to v2, highlighting breaking changes and providing code examples for clarity. 

## Breaking Changes

### 1. Endpoint Prefix Change
All API calls now include a version prefix. 

**Before:**
```http
GET /tasks
```
**After:**
```http
GET /v2/tasks
```

### 2. Authentication Header Change
The authentication method has changed from a custom header to a Bearer token. 

**Before:**
```http
X-Auth-Token: <your_api_key>
```
**After:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
Task IDs have changed from integers to UUID strings. 

**Before:**
```json
"id": 42
```
**After:**
```json
"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### 4. Task Field Renaming
The `done` field in task objects has been renamed to `completed`. 

**Before:**
```json
"done": false
```
**After:**
```json
"completed": false
```

### 5. Project ID Requirement
When creating a task, the `project_id` is now a required field. 

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

### 6. Paginated List Response
Responses from list endpoints now return a paginated envelope rather than a bare array.

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
1. Update endpoint URLs to include `/v2/` prefix.
2. Change the authentication header to use Bearer token format.
3. Update data models to reflect UUID type for `id`.
4. Rename the `done` field to `completed` in task objects.
5. Ensure all task creation requests include `project_id`.
6. Modify list handling to account for paginated responses.

## Upgrade Command
To upgrade Zrb CLI to v2, use the following command:
```bash
zrb upgrade
```  
