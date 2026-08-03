# Migrating to Zrb CLI v2

Zrb CLI v2 introduces architectural improvements including project-level organization, better pagination, and stricter security. Because these changes affect core data models and request structures, this is a breaking release.

## Breaking Changes

### 1. API Endpoint Versioning
All API endpoints are now prefixed with `/v2/`. Requests made to v1 endpoints will no longer be supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
The authentication mechanism has moved from a custom token header to a standard Bearer token.

**v1**
```
X-Auth-Token: <your_api_key>
```

**v2**
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID Data Type
Task IDs have changed from integers to UUID strings to support distributed task generation and project scoping.

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

### 5. Required `project_id` for Task Creation
Tasks must now be associated with a project. The `project_id` field is now mandatory when creating tasks.

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

### 6. Paginated Response Envelopes
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and pagination metadata.

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
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] **Update Base URL**: Prepend `/v2/` to all API request paths.
- [ ] **Update Auth**: Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] **Update ID Handling**: Update your data models to handle Task IDs as strings (UUIDs) instead of integers.
- [ ] **Update Field Names**: Rename all occurrences of `done` to `completed` in request and response bodies.
- [ ] **Add Project IDs**: Ensure `project_id` is provided in all `POST /v2/tasks` payloads.
- [ ] **Adjust List Parsing**: Update logic for list endpoints to read from the `.items` array instead of the root response.
- [ ] **Implement Pagination**: Use the `next_cursor` and `?cursor=` parameter to handle large result sets.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --to v2
```
