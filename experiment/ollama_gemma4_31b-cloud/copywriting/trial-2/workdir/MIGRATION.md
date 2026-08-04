# Migrating to Zrb CLI v2

This guide provides a detailed walkthrough for upgrading your integration from Zrb CLI v1 to v2. v2 introduces projects, improved pagination, and a more secure authentication scheme, but includes several breaking changes to the API structure and data models.

## Breaking Changes

### 1. Endpoint Versioning
All API endpoints have been moved to a versioned path. You must prefix all your request URLs with `/v2/`.

**v1**
```http
GET /tasks
```

**v2**
```http
GET /v2/tasks
```

### 2. Authentication Header
Authentication has moved from a custom header to the industry-standard Bearer token. Requests using the old header will now return `401 Unauthorized`.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Format
Task IDs have changed from integers to UUID strings to support better scaling and project isolation.

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

### 4. Field Rename: `done` → `completed`
The task status field has been renamed from `done` to `completed` for clarity.

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

### 5. Mandatory `project_id` for Creation
Tasks must now belong to a project. The `project_id` field is now required when creating a task; omitting it will result in a `422 Unprocessable Entity` response.

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
List endpoints no longer return a bare array. They now return a paginated envelope containing an `items` array and a `next_cursor`.

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
    {"id": "...", "title": "Buy milk", "completed": false},
    {"id": "...", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] Update local data models to treat Task IDs as strings (UUIDs) instead of integers.
- [ ] Rename all references of the `done` field to `completed` in your request and response handlers.
- [ ] Integrate project management to provide a `project_id` when calling the Create Task endpoint.
- [ ] Update list-handling logic to wrap results in the new paginated envelope and implement cursor-based pagination using `?cursor=`.

## Upgrade Command

To update your CLI tool to the latest version:

```bash
zrb upgrade --version v2
```
