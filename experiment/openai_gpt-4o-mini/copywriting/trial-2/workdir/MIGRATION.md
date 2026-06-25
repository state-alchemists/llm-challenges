# Zrb CLI Migration Guide from v1 to v2

## Overview
This migration guide outlines the breaking changes from version 1 (v1) to version 2 (v2) of the Zrb CLI API. It includes details on how to adapt your existing code and a checklist to facilitate a smooth transition.

## Breaking Changes

### 1. Endpoint URL Changes
**Description:** All endpoints are now prefixed with `/v2/`.

**Before:**
```plaintext
GET /tasks
```
**After:**
```plaintext
GET /v2/tasks
```

---

### 2. Authentication Header Change
**Description:** The authentication header has changed from `X-Auth-Token` to a Bearer token format.

**Before:**
```plaintext
X-Auth-Token: <your_api_key>
```
**After:**
```plaintext
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Changes
**Description:** The task `id` type has changed from an integer to a UUID string.

**Before:**
```json
{
  "id": 42,
}
```
**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
}
```

---

### 4. Field Renaming
**Description:** The `done` field in tasks has been renamed to `completed`.

**Before:**
```json
{
  "done": false,
}
```
**After:**
```json
{
  "completed": false,
}
```

---

### 5. Required Field in Task Creation
**Description:** The `project_id` is now a required field when creating a task.

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

---

### 6. Paginated List Response
**Description:** List endpoints now return a paginated envelope instead of a bare array.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false,
  "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true,
  "created_at": "..."}
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
2. Change your authentication mechanism to use the Bearer token format.
3. Update your task ID handling from integers to UUID strings.
4. Rename any references from `done` to `completed` in your task objects.
5. Add the `project_id` field to your task creation requests.
6. Adjust your handling of list responses to accommodate the paginated envelope.

## Upgrade Command
To upgrade to v2, run:
```bash
npm install zrb-cli@2
```