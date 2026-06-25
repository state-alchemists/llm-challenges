# Zrb Migration Guide from v1 to v2

This migration guide provides detailed instructions for developers transitioning from version 1 (v1) to version 2 (v2) of the Zrb Task API. The new version introduces several breaking changes, improved features, and stricter authentication processes.

---

## Breaking Changes Overview

1. **Endpoint Prefix Change:** All endpoints are now prefixed with `/v2/`.
2. **Authentication Header Change:** The authentication method has switched from `X-Auth-Token` to a Bearer token format.
3. **Task ID Type Change:** The `id` field in the task object is now a UUID string, previously an integer.
4. **Field Name Change:** The `done` field has been renamed to `completed`.
5. **Project Requirements:** Task creation now requires a `project_id` to be specified.
6. **Response Format Change:** List endpoints return a paginated envelope instead of a bare array.

---

## Detailed Migration Steps

### 1. Endpoint Prefix Change
All API calls must be updated to use the new prefix.

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
Update your authentication header from `X-Auth-Token` to Bearer token format.

**Before:**  
```http
X-Auth-Token: <your_api_key>
```  
**After:**  
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
The type of the `id` field has changed from an integer to a UUID string.

**Before:**  
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```  
**After:**  
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 4. Field Name Change
Change references of the field name `done` to `completed`.

**Before:**  
```json
{
  "title": "Updated title",
  "done": true
}
```  
**After:**  
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Project Requirements
Ensure that any task creation requests include the `project_id` field, which is now mandatory.

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

### 6. Response Format Change
Prepare to handle the new paginated response format for list endpoints.

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
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "...", "title": "Ship v1", "completed": true, "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist
1. Update all API endpoint URLs to include `/v2/`.
2. Change the authentication method to Bearer tokens.
3. Update the task ID handling from integers to UUID strings.
4. Rename the `done` field to `completed` in all relevant places.
5. Ensure that all task creation requests include a `project_id`.
6. Modify your application logic to handle the new paginated list responses.

---

## Upgrade Command
Run the following command to upgrade to the latest version of the Zrb CLI:
```sh
zrb upgrade --version 2.x
```  


Following these guidelines will ensure a smooth transition to version 2 of the Zrb Task API.