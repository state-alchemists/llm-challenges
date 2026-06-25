# Migrating to Zrb CLI v2

Zrb CLI v2 introduces structural changes to improve scalability, including project-based organization, robust pagination, and updated security standards. Because these changes alter the API contract, this is a breaking release.

## Breaking Changes

### 1. API Versioning
All endpoints have been moved under the `/v2/` prefix. Requests to v1 endpoints will no longer be supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
Authentication has moved from a custom header to the industry-standard Bearer token.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task Identifier Type
Task IDs have changed from integers to UUID strings to support distributed ID generation.

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
The `done` boolean field has been renamed to `completed` for better clarity.

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

### 5. Mandatory `project_id` for Creation
Tasks can no longer be created without an associated project. The `project_id` field is now required in the request body.

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
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and cursor information.

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
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Change authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to treat Task `id` as a string (UUID) instead of an integer.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Refactor list response handlers to parse the `.items` array from the paginated envelope.
- [ ] Implement cursor-based pagination using the `next_cursor` and `?cursor=` query parameter.

## Upgrade Command

To update your CLI to the latest version, run:

```bash
zrb update --version v2
```
