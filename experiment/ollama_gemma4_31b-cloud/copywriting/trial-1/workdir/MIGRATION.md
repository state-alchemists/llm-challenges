# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and organization. This guide will help you transition your existing v1 integrations to the new v2 API.

## Breaking Changes

### 1. API Endpoint Prefix
All API endpoints are now prefixed with `/v2/`. Requests made to v1 endpoints are no longer supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
The authentication mechanism has changed from a custom header to a standard Bearer token.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
Task identifiers have changed from integers to UUID strings to prevent ID exhaustion and improve security.

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

### 4. Task Completion Field
The `done` field has been renamed to `completed` for better clarity.

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

### 5. Required Project ID for Creation
To improve organization, all tasks must now be associated with a project. The `project_id` field is now required when creating a task.

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
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for subsequent pages.

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
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "proj_1"},
    {"id": "uuid-2", "title": "Ship v1", "completed": true, "project_id": "proj_1"}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] Update base API URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to handle `id` as a string (UUID) instead of an integer.
- [ ] Rename all references to the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Refactor list-fetching logic to handle the paginated envelope and implement cursor-based pagination.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --version 2.0.0
```
