# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including project-based organization and improved scalability via pagination. These changes include several breaking modifications to the API.

## Breaking Changes

### 1. API Versioning & Base Path
All API endpoints have been moved under a versioned prefix.

**v1:** `/tasks`
**v2:** `/v2/tasks`

```bash
# v1
curl https://api.zrb.io/tasks

# v2
curl https://api.zrb.io/v2/tasks
```

### 2. Authentication Header
The API has moved from a custom token header to the standard Bearer token authorization.

**v1:** `X-Auth-Token: <key>`
**v2:** `Authorization: Bearer <token>`

```http
# v1
X-Auth-Token: your_api_key

# v2
Authorization: Bearer your_api_token
```

### 3. Task ID Format
Task identifiers have changed from integers to UUID strings to support distributed ID generation.

**v1:** `42`
**v2:** `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`

```json
// v1
{ "id": 42 }

// v2
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" }
```

### 4. Field Rename: `done` to `completed`
The status field for tasks has been renamed for clarity.

**v1:** `done`
**v2:** `completed`

```json
// v1
{ "title": "Task", "done": true }

// v2
{ "title": "Task", "completed": true }
```

### 5. Required `project_id` for Creation
Tasks must now be associated with a project. The `project_id` field is now required when creating a task.

**v1:** `title` only
**v2:** `title` and `project_id`

```json
// v1
{ "title": "New task" }

// v2
{ 
  "title": "New task",
  "project_id": "proj_abc123" 
}
```

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

**v1:** `[...]`
**v2:** `{ "items": [...], "total": N, "next_cursor": "..." }`

```json
// v1
[
  { "id": 1, "title": "Task 1" },
  { "id": 2, "title": "Task 2" }
]

// v2
{
  "items": [
    { "id": "uuid-1", "title": "Task 1" },
    { "id": "uuid-2", "title": "Task 2" }
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update base URL paths to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Implement pagination logic to handle the new response envelope and `next_cursor` for list endpoints.

## Upgrade Command

To upgrade your CLI tool to the latest version, run:

```bash
zrb update --version v2
```
