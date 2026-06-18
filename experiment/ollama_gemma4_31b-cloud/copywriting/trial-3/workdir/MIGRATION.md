# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve API scalability, security, and data integrity. This guide will help you transition your integration from v1 to v2.

## Breaking Changes

### 1. API Endpoint Prefixing
All API endpoints are now prefixed with `/v2/`. Any requests sent to the v1 root paths will no longer be supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Method
Authentication has moved from a custom header to the industry-standard Bearer token. Requests using the old header will return `401 Unauthorized`.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
Task IDs have changed from integers to UUID strings to prevent ID enumeration and support distributed systems.

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

### 4. Field Rename: `done` → `completed`
The `done` boolean field has been renamed to `completed` for better clarity.

**v1**
```json
{
  "title": "Update docs",
  "done": true
}
```

**v2**
```json
{
  "title": "Update docs",
  "completed": true
}
```

---

### 5. Required `project_id` for Task Creation
Tasks must now be associated with a project. The `project_id` field is now mandatory during creation; omitting it will result in an `HTTP 422 Unprocessable Entity`.

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

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for subsequent requests.

**v1**
```json
[
  {"id": 1, "title": "Task 1", "done": false},
  {"id": 2, "title": "Task 2", "done": true}
]
```

**v2**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Task 1", "completed": false},
    {"id": "uuid-2", "title": "Task 2", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] Update data models to handle `id` as a string (UUID) instead of an integer.
- [ ] Rename `done` field references to `completed` across your codebase.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-fetching logic to handle the new paginated envelope and `next_cursor`.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb update --version v2
```
