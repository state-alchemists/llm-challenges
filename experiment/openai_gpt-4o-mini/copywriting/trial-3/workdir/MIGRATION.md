# Zrb CLI Migration Guide from v1 to v2

## Introduction
This guide provides comprehensive instructions for migrating from Zrb CLI v1 to v2. The new v2 version introduces several breaking changes that developers need to be aware of when transitioning their applications.

## Breaking Changes Summary

1. **Endpoint Prefix**: All endpoints are now prefixed with `/v2/`.
2. **Authentication Header**: The authentication header has changed.
3. **Task ID Type**: `id` field changed from integer to UUID string.
4. **Field Naming**: Task field `done` has been renamed to `completed`.
5. **Required Fields**: Task creation now requires `project_id`.
6. **Paginated Responses**: List endpoints now return a paginated envelope instead of a bare array.

## Migration Details

### 1. Endpoint Prefix
- **Before**:
    ```http
    GET /tasks
    ```
- **After**:
    ```http
    GET /v2/tasks
    ```

### 2. Authentication Header
- **Before**:
    ```http
    X-Auth-Token: <your_api_key>
    ```
- **After**:
    ```http
    Authorization: Bearer <your_api_token>
    ```
    Requests with the old header will return HTTP 401.

### 3. Task ID Type
- **Before**: The ID type was an integer.
- **After**: The ID type is now a UUID string.

Example conversion:
- **Before**:
    ```json
    {
      "id": 42
    }
    ```
- **After**:
    ```json
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    }
    ```

### 4. Field Naming Change
- **Before**:
    ```json
    {
      "done": false
    }
    ```
- **After**:
    ```json
    {
      "completed": false
    }
    ```

### 5. Required Field in Task Creation
Task creation now requires the `project_id` field.
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
    Omitting `project_id` will return HTTP 422.

### 6. Paginated List Envelope
List endpoints now return a paginated structure instead of a bare array.
- **Before**:
    ```json
    [
      {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
      {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
    ]
    ```
- **After**:
    ```json
    {
      "items": [...],
      "total": 42,
      "next_cursor": "cursor_xyz"
    }
    ```
    Use `?cursor=<next_cursor>` to fetch the next page.

## Step-by-Step Migration Checklist
1. Update API endpoint paths to include `/v2/`.
2. Change authentication method from `X-Auth-Token` to Bearer token.
3. Update any handling of task IDs from integers to UUID strings.
4. Rename the `done` field to `completed` in task objects.
5. Ensure all task creation requests include `project_id`.
6. Adjust any logic handling list responses to manage paginated envelopes.

## Upgrade Command
To upgrade your Zrb CLI to the latest version, run:
```bash
npm install zrb@latest
```