# Zrb CLI Migration Guide from v1 to v2

## Overview
This migration guide helps developers transition from Zrb CLI v1 to v2. It highlights breaking changes, provides code examples, and presents a checklist for migration.

## Breaking Changes

### 1. API Endpoints Prefix
All endpoints are now prefixed with `/v2/`. 
**Before:**
```plaintext
GET /tasks
```
**After:**
```plaintext
GET /v2/tasks
```  

### 2. Authentication Header Change
The authentication header has changed from `X-Auth-Token` to `Authorization` with a Bearer token. 
**Before:**
```plaintext
X-Auth-Token: <your_api_key>
```
**After:**
```plaintext
Authorization: Bearer <your_api_token>
``` 

### 3. Task ID Type Change
The `id` field of the Task object has changed from an integer to a UUID string.
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

### 4. Task Field Renamed
The field `done` has been renamed to `completed` in the Task object.
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

### 5. Required Project ID Field
Task creation now requires a `project_id` in the request body.
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
List endpoints now return a paginated response envelope instead of a direct array of tasks.
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
  "items": [
    {"id": "1", "title": "Buy milk"},
    {"id": "2", "title": "Ship v1"}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update all API endpoint URLs to include `/v2/`
2. Change authentication method to use Bearer tokens.
3. Update Task ID types from integers to UUID strings.
4. Rename the `done` field to `completed` in Task objects.
5. Ensure `project_id` is present in Task creation requests.
6. Modify client code to handle paginated list responses.

## Upgrade Command
To upgrade Zrb CLI to v2, run:
```bash
zrb upgrade --version 2.0.0
``` 

Ensure you thoroughly test your applications after migration to address any unforeseen issues.