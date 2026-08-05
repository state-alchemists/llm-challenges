# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and project organization. This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Endpoint Prefixing
All API endpoints now require a `/v2/` prefix.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
The authentication mechanism has moved from a custom header to a standard Bearer token.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
Task IDs have transitioned from integers to UUID strings to ensure uniqueness across distributed systems.

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
The boolean field used to track task status has been renamed for clarity.

**v1**
```json
{
  "title": "Ship v1",
  "done": true
}
```

**v2**
```json
{
  "title": "Ship v1",
  "completed": true
}
```

### 5. Required `project_id` on Creation
Tasks must now be associated with a project. The `project_id` field is now mandatory when creating a task.

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
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for subsequent requests.

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
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Update authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to treat Task IDs as strings (UUIDs) instead of integers.
- [ ] Rename all references to the `done` field to `completed` in request and response bodies.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-endpoint handlers to parse the `items` array from the new paginated envelope.
- [ ] Implement cursor-based pagination using `next_cursor`.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --version v2
```
