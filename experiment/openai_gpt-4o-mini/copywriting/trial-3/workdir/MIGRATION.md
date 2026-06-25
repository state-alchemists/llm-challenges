# Zrb Task API Migration Guide from v1 to v2

This migration guide outlines the changes from Zrb Task API v1 to v2, highlighting the breaking changes and providing examples to facilitate your transition. Follow the checklist at the end for a smooth migration.

## Breaking Changes

### 1. Endpoint Versioning
**Change:** All endpoints are now prefixed with `/v2/`.

**Before:**
```http
GET /tasks
```
**After:**
```http
GET /v2/tasks
```

---

### 2. Authentication Header Change
**Change:** The authentication method has changed from using `X-Auth-Token` to a Bearer token.

**Before:**
```
X-Auth-Token: <your_api_key>
```
**After:**
```
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
**Change:** The `id` field type has changed from an integer to a UUID string.

**Before:**
```json
{
  "id": 42
}
```
**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

### 4. Task Field Renaming
**Change:** The field `done` has been renamed to `completed`.

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

---

### 5. Required Project ID for Task Creation
**Change:** Task creation now requires a `project_id`.

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

### 6. Paginated List Responses
**Change:** List endpoints now return a paginated envelope instead of a bare array.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, ...},
  {"id": 2, "title": "Ship v1", "done": true, ...}
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

## Step-by-Step Migration Checklist
1. Update all API calls to include the `/v2/` prefix.
2. Change the authentication header to use Bearer tokens.
3. Update task `id` handling from integers to UUID strings.
4. Rename any `done` fields to `completed` in task objects.
5. Ensure that `project_id` is included in task creation requests.
6. Modify your handling of list responses to accommodate the new paginated structure.

## Upgrade Command
To upgrade to v2, use the following command:
```bash
zrb upgrade --version 2.0.0
```

Please ensure you test your application thoroughly after making these changes.