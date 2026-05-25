# Zrb Task API v1 to v2 Migration Guide

## Introduction

This guide is for experienced developers migrating from Zrb Task API v1 to v2. It explains significant breaking changes, provides before/after code examples, and offers a step-by-step migration checklist.

## Breaking Changes

### 1. Endpoint Prefix

All endpoints are now prefixed with `/v2/`.

**v1 Example:**
```http
GET /tasks
```

**v2 Example:**
```http
GET /v2/tasks
```

### 2. Authentication Header

The authentication header has been changed.

**v1:**
```http
X-Auth-Token: <your_api_key>
```

**v2:**
```http
Authorization: Bearer <your_api_token>
```

Requests using `X-Auth-Token` will now receive HTTP 401.

### 3. Task `id` Type

The `id` field type has changed from integer to UUID string.

**v1 Example:**
```json
"id": 42
```

**v2 Example:**
```json
"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### 4. Task Field Renamed

The `done` field has been renamed to `completed`.

**v1 Example:**
```json
"done": false
```

**v2 Example:**
```json
"completed": false
```

### 5. `project_id` Required for Task Creation

Creating a task now requires a `project_id`.

**v1 Example:**
```json
{
  "title": "New task title"
}
```

**v2 Example:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Omitting `project_id` returns HTTP 422.

### 6. Paginated List Responses

List endpoints now return a paginated envelope rather than a bare array.

**v1 Example:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."}
]
```

**v2 Example:**
```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890", "title": "Buy milk", "completed": false, "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

1. **Update Endpoint Prefixes:** Add `/v2/` to all endpoints.
2. **Change Authentication Header:** Switch to the Bearer token.
3. **Modify Task `id` Field:** Ensure IDs use UUID strings.
4. **Rename `done` to `completed`:** Update field names in requests and logic.
5. **Include `project_id` on Task Creation:** Ensure all creation requests have a valid `project_id`.
6. **Adjust for Paginated Responses:** Update client code to handle the paginated envelope structure.

## Upgrade Command

Run the following command to upgrade your installation to Zrb CLI v2:

```bash
zrb upgrade --version 2
```
