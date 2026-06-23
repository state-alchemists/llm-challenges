# Migrating to Zrb CLI v2

Zrb v2 introduces several breaking changes to improve scalability and project organization. This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Endpoint Prefix
All endpoints now require the `/v2/` prefix.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
Authentication has moved from a custom header to the industry-standard Bearer token format.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task Identifier Type
Task IDs have changed from integers to UUID strings to support distributed scaling.

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

### 4. Task Status Field Rename
The `done` field has been renamed to `completed` for better clarity.

**v1**
```json
{
  "id": 42,
  "done": false
}
```

**v2**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "completed": false
}
```

---

### 5. Required Project ID for Creation
Tasks must now be associated with a project. The `project_id` field is now required when creating a task.

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
List endpoints no longer return a bare array. They now return a paginated envelope.

**v1**
```json
[
  {"id": 1, "title": "Task 1"},
  {"id": 2, "title": "Task 2"}
]
```

**v2**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Task 1"},
    {"id": "uuid-2", "title": "Task 2"}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Switch authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to treat Task IDs as strings (UUIDs) instead of integers.
- [ ] Rename all references to the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-fetching logic to handle the paginated envelope (`items` array and `next_cursor`).

## Upgrade Command

To update your Zrb CLI to the latest version, run:

```bash
zrb update --version 2.0.0
```
