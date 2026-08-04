# Zrb CLI v2 Migration Guide

The Zrb CLI has been updated to v2. This release introduces significant architectural improvements, including project-based organization and enhanced pagination, but includes several breaking changes to the API and authentication.

## Breaking Changes

### 1. API Versioning
All endpoints are now versioned. You must prefix all request paths with `/v2/`.

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

### 3. Task Identifier Type
Task IDs have changed from integers to UUID strings to support better distributed scaling.

**v1**
`GET /tasks/42`

**v2**
`GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890`

### 4. Task Status Field Rename
The `done` field has been renamed to `completed` for clarity.

**v1**
```json
{
  "id": 42,
  "done": true
}
```

**v2**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "completed": true
}
```

### 5. Required Project Association
Tasks can no longer be created globally. A `project_id` is now required during task creation.

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

### 6. Paginated Response Envelope
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and navigation metadata.

**v1**
```json
[
  {"id": 1, "title": "Buy milk", ...},
  {"id": 2, "title": "Ship v1", ...}
]
```

**v2**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", ...},
    {"id": "uuid-2", "title": "Ship v1", ...}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Migrate authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Replace all references to the `done` field with `completed`.
- [ ] Update Task creation logic to include a valid `project_id`.
- [ ] Update list-fetching logic to parse the `items` array from the new response envelope.
- [ ] Implement cursor-based pagination using the `next_cursor` field.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb update --version v2
```
