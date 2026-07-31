# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including project-based organization and enhanced pagination. To support these changes, several breaking changes have been introduced to the API.

## Breaking Changes

### 1. API Versioning
All endpoints are now prefixed with `/v2/`. Requests to v1 endpoints are no longer supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
Authentication has moved from a custom header to a standard Bearer token.

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

### 4. Task Status Field
The `done` field has been renamed to `completed` for better clarity.

**v1**
```json
{
  "title": "Write tests",
  "done": true
}
```

**v2**
```json
{
  "title": "Write tests",
  "completed": true
}
```

### 5. Required Project ID
Tasks must now be associated with a project. The `project_id` field is now required during task creation.

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
  {"id": 1, "title": "Buy milk", "completed": false},
  {"id": 2, "title": "Ship v1", "completed": true}
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
- [ ] Switch authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Rename all occurrences of the `done` field to `completed`.
- [ ] Ensure `project_id` is provided when creating new tasks.
- [ ] Update list request logic to handle the new paginated envelope and implement cursor-based pagination.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --version v2
```
