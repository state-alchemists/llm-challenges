### Project Management API
 This API allows users to manage projects and tasks efficiently. 

 #### Authentication
 The API uses an `X-API-Key` for authentication, where valid keys are stored in the database.

 #### Endpoints
 - `GET /projects`: List all projects.
 - `GET /tasks`: List tasks with optional filtering by `status`, `priority`, and `assigned_to`.
   - Supports pagination with `page` and `page_size`.
 - `POST /tasks`: Create a new task (Requires authentication) and validates that the associated project exists.
 - `PUT /tasks/{task_id}`: Update an existing task (Requires authentication).
 - `DELETE /tasks/{task_id}`: Delete a specific task (Requires authentication).