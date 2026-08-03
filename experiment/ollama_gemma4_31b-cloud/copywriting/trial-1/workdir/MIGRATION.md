# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including project-based organization and robust pagination. Because these changes alter the core API contract, this version is not backward compatible with v1.

## Breaking Changes

### 1. API Versioning
All endpoints are now prefixed with `/v2/`. Requests to v1 endpoints are no longer supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
Authentication has moved from a custom token header to a standard Bearer token format. Requests using the old header will receive a `401 Unauthorized` response.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type
Task IDs have changed from integers to UUID strings to support distributed scaling and avoid collisions.

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

---

### 4. Task Status Field
The `done` boolean has been renamed to `completed` for better clarity.

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

---

### 5. Mandatory Project Association
Tasks can no longer exist in a global namespace. Every task must now be associated with a project. Omitting `project_id` during creation will return a `422 Unprocessable Entity` error.

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

---

### 6. List Response Format
List endpoints no longer return a bare array. They now return a paginated envelope to ensure performance as your task list grows.

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

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Migrate authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to treat Task IDs as strings (UUIDs) instead of integers.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Ensure all `POST /v2/tasks` requests include a valid `project_id`.
- [ ] Update list-handling logic to extract tasks from the `.items` array and implement cursor-based pagination using `next_cursor`.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --to-v2
```
