# Zrb Task API v1 to v2 Migration Guide

This migration guide will help you transition your existing implementations from Zrb Task API v1 to v2, highlighting all breaking changes and providing before/after examples for a smooth upgrade.

## Breaking Changes

### 1. Endpoint Prefix Change

**Change:** All endpoints are now prefixed with `/v2/`.

**Before:**
```http
GET /tasks
```
**After:**
```http
GET /v2/tasks
```

### 2. Authentication Header Change

**Change:** Authentication now requires a Bearer token.

**Before:**
```http
X-Auth-Token: <your_api_key>
```
**After:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change

**Change:** Task `id` has changed from an integer to a UUID string.

**Before:**
```json
"id": 42
```
**After:**
```json
"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### 4. Task Field Renaming

**Change:** The `done` field is renamed to `completed`.

**Before:**
```json
"done": false
```
**After:**
```json
"completed": false
```

### 5. Task Creation Requirement

**Change:** `project_id` is now required when creating a task.

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

### 6. List Endpoint Pagination

**Change:** List endpoints return a paginated envelope instead of a bare array.

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
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false},
    {"id": "b2c3d4e5-f6a7-8901-abcd-ef2345678901", "title": "Ship v2", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

1. **Update Endpoint Prefixes**: Ensure all API calls use the `/v2/` prefix.
2. **Change Authentication Headers**: Replace `X-Auth-Token` with Bearer token in headers.
3. **Modify Task ID Handling**: Update code to use string-based UUIDs for task IDs.
4. **Rename Task Field**: Change any instances of `done` to `completed` in your codebase.
5. **Ensure Project ID on Task Creation**: Add `project_id` field in all task creation requests.
6. **Implement Pagination**: Adjust logic to handle paginated responses from list endpoints.

## Upgrade Command

To upgrade your Zrb CLI to v2, run:

```bash
zrb upgrade --version 2.0
```

This guide ensures that you understand and incorporate all necessary changes to seamlessly upgrade from v1 to v2 of the Zrb Task API. Follow the checklist step-by-step to avoid common pitfalls during the transition. Happy coding!
