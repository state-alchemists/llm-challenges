# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including project-based task organization and improved pagination. To support these changes, v2 includes several breaking changes to the API and authentication model.

This guide will help you migrate your integration from v1 to v2.

## Breaking Changes

### 1. API Versioning (Endpoint Prefix)
All API endpoints are now prefixed with `/v2/`. Requests to v1 endpoints are no longer supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
Authentication has moved from a custom token header to a standard Bearer token.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Format
Task IDs have changed from integers to UUID strings to ensure uniqueness across projects.

**v1**
```json
{
  "id": 42,
  "title": "Write tests"
}
```

**v2**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. Field Rename: `done` $\rightarrow$ `completed`
The boolean field indicating task completion has been renamed for clarity.

**v1**
```json
{
  "title": "Update docs",
  "done": true
}
```

**v2**
```json
{
  "title": "Update docs",
  "completed": true
}
```

### 5. Required `project_id` on Creation
Tasks must now be associated with a project. The `project_id` field is now required when creating a task.

**v1**
```json
{
  "title": "New task"
}
```

**v2**
```json
{
  "title": "New task",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

**v1**
```json
[
  {"id": 1, "title": "Task 1", ...},
  {"id": 2, "title": "Task 2", ...}
]
```

**v2**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Task 1", ...},
    {"id": "uuid-2", "title": "Task 2", ...}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to treat Task IDs as strings (UUIDs) instead of integers.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-fetching logic to handle the new paginated envelope (`items` array).
- [ ] Implement cursor-based pagination using the `next_cursor` value.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --version v2
```
