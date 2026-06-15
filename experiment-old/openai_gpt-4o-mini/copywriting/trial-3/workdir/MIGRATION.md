# Migration Guide from Zrb v1 to v2

## Introduction
This migration guide is designed for developers currently using Zrb API v1, detailing the breaking changes in Zrb API v2 and providing a clear path for upgrading.

## Breaking Changes

1. **Endpoint Changes**  
   All endpoints are now prefixed with `/v2/`.
   
   **Before:**  
   ```plaintext
   GET /tasks
   ```  
   **After:**  
   ```plaintext
   GET /v2/tasks
   ```
   
2. **Authentication Header**  
   The required authentication header has changed from `X-Auth-Token` to a Bearer token.
   
   **Before:**  
   ```plaintext
   X-Auth-Token: <your_api_key>
   ```  
   **After:**  
   ```plaintext
   Authorization: Bearer <your_api_token>
   ```

3. **Task ID Type**  
   The `id` field of tasks has transitioned from an integer to a UUID string.
   
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

4. **Task Field Rename**  
   The `done` field in the task object has been renamed to `completed`.
   
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

5. **Required Project ID**  
   Task creation now requires the `project_id` in the request body.
   
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

6. **Paginated List Endpoint Response**  
   List endpoints now return a paginated envelope instead of a bare array.
   
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
     "items": [...],
     "total": 42,
     "next_cursor": "cursor_xyz"
   }
   ```

## Migration Checklist
1. Update all API endpoint usages to include the `/v2/` prefix.
2. Change your authentication method to use the Bearer token format.
3. Update any task object references to use UUID strings for `id`.
4. Replace `done` with `completed` in all relevant places in your code.
5. Ensure that `project_id` is included in all task creation requests.
6. Modify your code to handle the new paginated response structure for list endpoints.

## Upgrade Command
To upgrade to v2, run the following command:
```bash
zrb upgrade
```