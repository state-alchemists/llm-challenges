# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and organization. This guide will help you migrate your integrations from v1 to v2.

## Breaking Changes

### 1. API Versioning
All endpoints are now prefixed with `/v2/`.

**v1 Request:**
`GET /tasks`

**v2 Request:**
`GET /v2/tasks`

### 2. Authentication Header
The authentication header has changed from a custom token to a standard Bearer token. Requests using the old header will now receive an `HTTP 401 Unauthorized` response.

**v1 Header:**
```http
X-Auth-Token: <your_api_key>
```

**v2 Header:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
Task IDs have changed from integers to UUID strings to prevent ID enumeration and support distributed systems.

**v1 Task:**
```json
{
  "id": 42,
  "title": "Write tests"
}
```

**v2 Task:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. Field Rename: `done` → `completed`
The `done` field has been renamed to `completed` for better clarity.

**v1 Task:**
```json
{
  "title": "Write tests",
  "done": false
}
```

**v2 Task:**
```json
{
  "title": "Write tests",
  "completed": false
}
```

### 5. Required `project_id` on Creation
Tasks must now be associated with a project. The `project_id` field is now required when creating a task. Omitting it will result in an `HTTP 422 Unprocessable Entity` response.

**v1 Request Body:**
```json
{
  "title": "New task title"
}
```

**v2 Request Body:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

**v1 Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**v2 Response:**
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

- [ ] Update all API endpoint URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to handle Task IDs as UUID strings instead of integers.
- [ ] Replace all references to the `done` field with `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-fetching logic to parse the `items` array from the new paginated envelope.
- [ ] Implement cursor-based pagination using the `next_cursor` and `?cursor=` query parameter.

## Upgrade Command

To update your CLI to the latest version, run:

```bash
zrb update --version v2
```
