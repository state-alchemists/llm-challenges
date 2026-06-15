# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve API scalability, security, and organizational structure. This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Versioning & Endpoints
All API endpoints are now version-prefixed. You must update your base URLs to include `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
Authentication has moved from a custom header to the industry-standard Bearer token format. Requests using the old header will return `401 Unauthorized`.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Format
Task identifiers have changed from integers to UUID strings to prevent ID exhaustion and improve security.

**v1**
`"id": 42`

**v2**
`"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"`

---

### 4. Task Status Field
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

---

### 5. Required Project Context
Tasks must now be associated with a project. The `project_id` field is now mandatory during task creation. Omitting this field will result in a `422 Unprocessable Entity` error.

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

### 6. List Response Format (Pagination)
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

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
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] Update data models to handle UUID strings for Task IDs instead of integers.
- [ ] Rename all references of the `done` field to `completed` in requests and responses.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-handling code to parse the `items` array from the new paginated envelope.
- [ ] Implement cursor-based pagination using the `next_cursor` and `?cursor=` query parameter.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --version v2
```
