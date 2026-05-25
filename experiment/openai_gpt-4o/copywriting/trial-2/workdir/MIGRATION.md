# Zrb CLI v2 Migration Guide

## Introduction

This guide will help you migrate your applications from Zrb CLI v1 to v2. It covers all breaking changes and provides examples to ensure a smooth transition.

## Breaking Changes

### 1. Endpoint Prefix

**Change**: All endpoints are now prefixed with `/v2/`.

**Before**:
```http
GET /tasks
```

**After**:
```http
GET /v2/tasks
```

### 2. Authentication Header

**Change**: The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer`.

**Before**:
```http
X-Auth-Token: <your_api_key>
```

**After**:
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Format

**Change**: Task `id` has changed from an integer to a UUID string.

**Before**:
```json
{
  "id": 42
}
```

**After**:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### 4. Renaming of Task Field

**Change**: The task field `done` is now `completed`.

**Before**:
```json
{
  "done": false
}
```

**After**:
```json
{
  "completed": false
}
```

### 5. Mandatory Project ID

**Change**: `project_id` is now a required field when creating tasks.

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

### 6. Paginated List Responses

**Change**: List endpoints now return a paginated envelope instead of a bare array.

**Before**:
```json
[
  {"id": 1, "title": "Buy milk", "done": false}
]
```

**After**:
```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

### Step-by-Step Migration Checklist

1. **Update Endpoints**: Change your API calls to use the `/v2/` prefix.
2. **Modify Authentication**: Switch to using the `Authorization: Bearer` header.
3. **Convert Task IDs**: Ensure your system handles UUID strings instead of integers for task IDs.
4. **Rename Task Fields**: Update any logic using the `done` field to use `completed`.
5. **Add Project ID**: Include `project_id` in task creation requests.
6. **Handle Pagination**: Adjust your logic to process paginated responses.

### Upgrade Command

To upgrade to Zrb CLI v2, run the following command:
```bash
pip install zrb-cli==2.0.0
```

This comprehensive guide aims to address all potential hiccups you might encounter while migrating to v2. Follow each section carefully and update your codebase accordingly.
