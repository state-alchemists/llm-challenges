# Zrb CLI Migration Guide from v1 to v2

This guide outlines the breaking changes and necessary adjustments for migrating from version 1 to version 2 of the Zrb CLI API. It aims to help developers seamlessly transition to the new version by providing clear examples and a step-by-step checklist.

## Breaking Changes Summary

1. **Endpoint Prefix Change**  
   All endpoints are now prefixed with `/v2/`

2. **Authentication Header Change**  
   The authentication header has changed from `X-Auth-Token` to a Bearer token:
   ```plaintext
   Authorization: Bearer <your_api_token>
   ```  
   Requests utilizing the old header will now receive HTTP 401 errors.

3. **Task ID Type Change**  
   The `id` field type for tasks has changed from an integer to a UUID string.
   - **Before:** 
     ```json
     {
       "id": 42,
       "title": "Write tests",
       "done": false
     }
     ```  
   - **After:**  
     ```json
     {
       "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
       "title": "Write tests",
       "completed": false
     }
     ```

4. **Renaming of the `done` Field**  
   The `done` field has been renamed to `completed`.
   - **Before:** 
     ```json
     {
       "done": false
     }
     ```  
   - **After:**  
     ```json
     {
       "completed": false
     }
     ```

5. **Creation of Tasks Requires `project_id`**  
   When creating a task, the `project_id` is now required:
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

6. **Paginated List Response**  
   List endpoints now return a paginated envelope instead of a bare array:
   - **Before:**  
     ```json
     [
       {"id": 1, "title": "Buy milk", "done": false},
       {"id": 2, "title": "Ship v1", "done": true}
     ]
     ```  
   - **After:**  
     ```json
     {
       "items": [
         {"id": "...", "title": "...", "completed": false},
         {"id": "...", "title": "...", "completed": true}
       ],
       "total": 42,
       "next_cursor": "cursor_xyz"
     }
     ```

## Step-by-Step Migration Checklist
1. Update your API endpoints to use the `/v2/` prefix.
2. Replace the `X-Auth-Token` header with the `Authorization: Bearer <your_api_token>` header.
3. Modify task `id` references from integer to UUID strings wherever applicable.
4. Change the `done` field to `completed` in all relevant requests/responses.
5. Ensure that `project_id` is included in all task creation requests.
6. Adapt your handling of list endpoints to process the new paginated response structure.

## Upgrade Command

To upgrade to v2, use the following command:
```bash
zrb upgrade --version 2.0
```