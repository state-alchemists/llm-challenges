# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to the Task API to support projects, improved pagination, and stricter security. This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Versioning
All endpoints are now versioned. You must prefix all request paths with `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
The authentication mechanism has moved from a custom header to a standard Bearer token. Requests using the old header will now return `401 Unauthorized`.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
Task IDs have changed from integers to UUID strings. Update your data models and database schemas to support string-based IDs.

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

### 4. Field Renaming: `done` → `completed`
The boolean field indicating task status has been renamed for clarity.

**v1**
```json
{
  "title": "Write tests",
  "done": false
}
```

**v2**
```json
{
  "title": "Write tests",
  "completed": false
}
```

### 5. Required `project_id` on Creation
Tasks can no longer be created without being associated with a project. Omitting the `project_id` will now return `422 Unprocessable Entity`.

**v1**
```json
{
  "title": "New task title"
}
```

**v2**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

**v1**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**v2**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false},
    {"id": "uuid-2", "title": "Ship v1", "completed": true}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update Task ID types from `Integer` to `String/UUID` in your application code and database.
- [ ] Rename all references to the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list response parsing to handle the paginated envelope (`items`, `total`, `next_cursor`).
- [ ] Implement cursor-based pagination using the `?cursor=` query parameter.

## Upgrade Command

To update your CLI to the latest version:

```bash
zrb update --version v2
```
