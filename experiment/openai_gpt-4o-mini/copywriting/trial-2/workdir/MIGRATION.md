# Zrb Migration Guide: v1 to v2

This migration guide outlines the breaking changes introduced in version 2 of the Zrb Task API. It provides clear instructions and examples to help you transition from v1 to v2.

## Breaking Changes

### 1. Endpoint Prefix Change
- **Before:**  
  `GET /tasks`

- **After:**  
  `GET /v2/tasks`

### 2. Authentication Header Change
- **Before:**  
  ```
  X-Auth-Token: <your_api_key>
  ```
- **After:**  
  ```
  Authorization: Bearer <your_api_token>
  ```
Requests using `X-Auth-Token` will receive HTTP 401 errors.

### 3. Task ID Type Change
- **Before:**  
  ```json
  {
    "id": 42,
    "title": "Write tests",
    "done": false,
    "created_at": "2024-01-15T10:30:00Z"
  }
  ```
- **After:**  
  ```json
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "title": "Write tests",
    "completed": false,
    "project_id": "proj_abc123",
    "created_at": "2024-01-15T10:30:00Z"
  }
  ```
The `id` type changed from integer to UUID string.

### 4. Field Name Change: `done` to `completed`
- **Before:**  
  ```json
  {
    "title": "Task Title",
    "done": true
  }
  ```
- **After:**  
  ```json
  {
    "title": "Task Title",
    "completed": true
  }
  ```

### 5. Task Creation Requires `project_id`
- **Before:**  
  ```json
  {
    "title": "New task title"
  }
  ```
- **After:**  
  ```json
  {
    "title": "New task title",
    "project_id": "proj_abc123"
  }
  ```
`project_id` is now required for creating a task.

### 6. List Endpoints Return Paginated Envelope
- **Before Response:**  
  ```json
  [
    {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
    {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
  ]
  ```
- **After Response:**  
  ```json
  {
    "items": [...],
    "total": 42,
    "next_cursor": "cursor_xyz"
  }
  ```
All list responses now return a paginated envelope.

## Migration Checklist
1. Update endpoint URLs from `/tasks` to `/v2/tasks`.
2. Change the authentication header to use the Bearer token format.
3. Modify code to handle UUID strings for task IDs.
4. Rename `done` fields to `completed`.
5. Ensure `project_id` is included in task creation requests.
6. Adjust handling of list responses to manage paginated results.

## Upgrade Command
To upgrade to v2, use the following command:

```bash
zrb upgrade
```