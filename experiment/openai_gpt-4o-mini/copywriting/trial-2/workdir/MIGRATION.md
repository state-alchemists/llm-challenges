# Zrb CLI Migration Guide from v1 to v2

This guide outlines the breaking changes and migration steps for developers transitioning from Zrb CLI v1 to v2.

## Breaking Changes

### 1. Endpoint Prefixing
All API endpoints are now prefixed with `/v2/`.

#### Before:
```
GET /tasks
```
#### After:
```
GET /v2/tasks
```

---

### 2. Authentication Header Change
The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer`.

#### Before:
```
X-Auth-Token: <your_api_key>
```
#### After:
```
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
The `id` field in the Task object has changed from an integer to a UUID string.

#### Before:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```
#### After:
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

### 4. Renaming of Task Field
The field `done` has been renamed to `completed`.

#### Before:
```json
{
  "done": false
}
```
#### After:
```json
{
  "completed": false
}
```

---

### 5. Required Project ID in Task Creation
Creating a task now requires the `project_id` field.

#### Before:
```json
{
  "title": "New task title"
}
```
#### After:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Pagination in List Endpoints
List endpoints now return a paginated envelope instead of a bare array, requiring cursors for pagination.

#### Before:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."}
]
```
#### After:
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist
1. Update all API endpoint URLs to include the `/v2/` prefix.
2. Change the authentication header to use `Authorization: Bearer`.
3. Modify the handling of `id` fields from integers to UUID strings.
4. Rename any instances of `done` to `completed` in task objects.
5. Ensure that `project_id` is included in the task creation requests.
6. Update any code that handles the response from list endpoints to accommodate the new paginated format.

## Upgrade Command
Execute the following command to upgrade to Zrb v2:
```
npm install zrb@latest
```