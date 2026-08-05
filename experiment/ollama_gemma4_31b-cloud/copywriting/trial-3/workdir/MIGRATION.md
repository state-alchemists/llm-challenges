# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve API scalability, security, and data integrity. This guide will help you transition your integration from v1 to v2.

## Breaking Changes

### 1. API Version Prefix
All endpoints are now versioned. You must prefix your request paths with `/v2/`.

**v1:**
`GET /tasks`

**v2:**
`GET /v2/tasks`

### 2. Authentication Header
The authentication mechanism has moved from a custom header to a standard Bearer token.

**v1:**
```http
X-Auth-Token: <your_api_key>
```

**v2:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
Task IDs have transitioned from integers to UUID strings for better distributed uniqueness.

**v1:**
```json
{
  "id": 42,
  "title": "Write tests"
}
```

**v2:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. Field Rename: `done` → `completed`
The `done` boolean field has been renamed to `completed` for clarity.

**v1:**
```json
{
  "id": 42,
  "done": false
}
```

**v2:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "completed": false
}
```

### 5. Mandatory `project_id` for Task Creation
Tasks must now be associated with a project. The `project_id` field is now required when creating a task.

**v1:**
```json
{
  "title": "New task title"
}
```

**v2:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated Response Envelopes
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and cursor information.

**v1:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**v2:**
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

---

## Migration Checklist

- [ ] Update all API endpoint paths to include the `/v2/` prefix.
- [ ] Switch authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to handle `id` as a string (UUID) instead of an integer.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-processing logic to extract data from the `items` array in the response envelope.
- [ ] Implement cursor-based pagination for list requests using the `next_cursor`.

## Upgrade Command

To upgrade your Zrb CLI to the latest version, run:

```bash
zrb update --version v2
```
