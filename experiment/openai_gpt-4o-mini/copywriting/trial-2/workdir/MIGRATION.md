# Zrb CLI v2 Migration Guide

## Introduction
Welcome to the Zrb CLI v2 migration guide. This guide details the breaking changes from v1 to v2 and provides developers with the necessary steps to update their code.

## Breaking Changes
### 1. Endpoint Prefix
- **Change**: All endpoints are now prefixed with `/v2/`.
- **Before**:
  ```http
  GET /tasks
  ```
- **After**:
  ```http
  GET /v2/tasks
  ```

### 2. Authentication Header
- **Change**: The authentication header has changed from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
- **Before**:
  ```http
  X-Auth-Token: <your_api_key>
  ```
- **After**:
  ```http
  Authorization: Bearer <your_api_token>
  ```

### 3. Task ID Type Change
- **Change**: The task `id` type has changed from integer to UUID string.
- **Before**:
  ```json
  {
    "id": 42,
  }
  ```
- **After**:
  ```json
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  }
  ```

### 4. Task Field Renaming
- **Change**: The `done` field has been renamed to `completed`.
- **Before**:
  ```json
  {
    "done": false,
  }
  ```
- **After**:
  ```json
  {
    "completed": false,
  }
  ```

### 5. Project ID Requirement
- **Change**: Task creation now requires a `project_id`.
- **Before**:
  ```json
  {
    "title": "New task title"
  }
  ```
- **After**:
  ```json
  {
    "title": "New task title",
    "project_id": "proj_abc123"
  }
  ```

### 6. Paginated List Responses
- **Change**: List endpoints now return a paginated envelope instead of a bare array.
- **Before**:
  ```json
  [
    {"id": 1, "title": "Buy milk", "done": false},
    {"id": 2, "title": "Ship v1", "done": true}
  ]
  ```
- **After**:
  ```json
  {
    "items": [
      {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false},
      {"id": "b1c2d3e4-f5g6-7890-abcd-ef1234567890", "title": "Ship v1", "completed": true}
    ],
    "total": 2,
    "next_cursor": "cursor_xyz"
  }
  ```

## Migration Checklist
1. Update endpoint URLs to start with `/v2/`.
2. Replace authentication header `X-Auth-Token` with `Authorization: Bearer <your_api_token>`.
3. Change the task `id` field from an integer to a UUID string in all relevant code.
4. Rename the `done` field to `completed` in task objects.
5. Include the `project_id` field when creating new tasks.
6. Adjust handling for task list responses to accommodate the new paginated format.

## Upgrade Command
To upgrade to v2, use the following command:
```bash
npm install zrb-cli@latest
```

---