# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary steps to migrate your existing Zrb CLI integrations from v1 to v2. Version 2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication, which require changes to your existing code.

## Summary of Breaking Changes

1.  **Endpoint Path Prefix**: All API endpoints are now prefixed with `/v2/`.
2.  **Authentication Header**: The authentication mechanism has changed.
3.  **Task ID Type**: Task IDs are now UUID strings instead of integers.
4.  **Task Field Renamed**: The `done` field has been renamed to `completed`.
5.  **Project Requirement for Task Creation**: Creating a task now requires a `project_id`.
6.  **Paginated List Responses**: List endpoints now return a paginated envelope rather than a bare array.

---

## Detailed Breaking Changes and Migration Steps

### 1. Endpoint Path Prefix

All v2 endpoints are now located under the `/v2/` path.

**Before (v1):**

```
GET /tasks
POST /tasks
GET /tasks/{id}
```

**After (v2):**

```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
```

**Migration:** Update all API call URLs to include the `/v2/` prefix.

### 2. Authentication Header

The authentication header has changed from `X-Auth-Token` to a standard Bearer token.

**Before (v1):**

```python
headers = {
    "X-Auth-Token": "YOUR_V1_API_KEY"
}
```

**After (v2):**

```python
headers = {
    "Authorization": "Bearer YOUR_V2_API_TOKEN"
}
```

**Migration:**
- Obtain a new v2 API token.
- Update your application's authentication logic to use the `Authorization: Bearer` header.

### 3. Task ID Type

Task `id`s have transitioned from integers to UUID strings.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Old Task"
}
```

```python
task_id = 42
response = client.get(f"/tasks/{task_id}")
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "New Task"
}
```

```python
task_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
response = client.get(f"/v2/tasks/{task_id}")
```

**Migration:** Update any code that stores, retrieves, or manipulates task IDs to expect and handle UUID strings instead of integers.

### 4. Task Field Renamed: `done` to `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Buy milk",
  "done": false
}
```

```python
task_data = {"done": True}
response = client.put(f"/tasks/{task_id}", json=task_data)
```

**After (v2):**

```json
{
  "id": "...",
  "title": "Buy milk",
  "completed": false
}
```

```python
task_data = {"completed": True}
response = client.put(f"/v2/tasks/{task_id}", json=task_data)
```

**Migration:** Update all code referencing the `done` field to use `completed` instead, in both request bodies and response parsing.

### 5. Task Creation Requires `project_id`

When creating new tasks, a `project_id` (string) is now a mandatory field in the request body.

**Before (v1):**

```python
create_data = {"title": "New task title"}
response = client.post("/tasks", json=create_data)
```

**After (v2):**

```python
create_data = {
    "title": "New task title",
    "project_id": "proj_abc123" # Required
}
response = client.post("/v2/tasks", json=create_data)
```

**Migration:**
- Ensure all task creation requests include a valid `project_id`.
- You may need to create a project first or retrieve an existing `project_id`.

### 6. Paginated List Responses

List endpoints (e.g., `GET /v2/tasks`) no longer return a bare array. Instead, they return a paginated envelope containing `items`, `total`, and `next_cursor`.

**Before (v1):**

```json
[
  {"id": 1, "title": "Task A"},
  {"id": 2, "title": "Task B"}
]
```

```python
response = client.get("/tasks")
tasks = response.json() # Direct access to list of tasks
for task in tasks:
    print(task["title"])
```

**After (v2):**

```json
{
  "items": [
    {"id": "...", "title": "Task A"},
    {"id": "...", "title": "Task B"}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

```python
response = client.get("/v2/tasks")
paginated_data = response.json()
tasks = paginated_data["items"] # Access tasks via the 'items' key
for task in tasks:
    print(task["title"])

next_page_cursor = paginated_data.get("next_cursor")
if next_page_cursor:
    # Fetch next page: client.get(f"/v2/tasks?cursor={next_page_cursor}")
    pass
```

**Migration:**
- Update your code to access the list of tasks from the `items` key within the response object.
- Implement pagination logic using the `next_cursor` field and the `cursor` query parameter for subsequent requests.

---

## Migration Checklist

- [ ] Update all API endpoint URLs to include the `/v2/` prefix.
- [ ] Obtain a new v2 API token.
- [ ] Change authentication header from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update task ID handling to expect UUID strings instead of integers.
- [ ] Rename all references to the `done` field to `completed`.
- [ ] Modify task creation requests to include a `project_id` in the request body.
- [ ] Adjust parsing logic for list responses to extract tasks from the `items` array of the paginated envelope.
- [ ] (Optional) Implement pagination using `cursor` and `next_cursor` for list endpoints.

## Upgrade Command

To ensure your Zrb CLI is updated to the latest v2 version, run:

```bash
zrb upgrade --version 2
```
