# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and organization. This guide will help you transition your integration from v1 to v2.

## Breaking Changes

### 1. API Versioning and Base URLs
All endpoints have been namespaced. You must now prefix your request paths with `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Method
The authentication header has changed from a custom token to a standard Bearer token.

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
Task IDs have migrated from integers to UUID strings to prevent ID enumeration and improve distributed consistency.

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

### 4. Field Renaming: `done` → `completed`
The boolean field indicating task completion has been renamed for clarity.

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
Tasks can no longer exist in isolation. A `project_id` is now required when creating a task.

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
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

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
    {"id": "...", "title": "Buy milk", "completed": false},
    {"id": "...", "title": "Ship v1", "completed": true}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to handle UUID strings for task IDs instead of integers.
- [ ] Replace all references to the `done` field with `completed`.
- [ ] Update task creation logic to provide a valid `project_id`.
- [ ] Update list-handling logic to parse the paginated envelope (`items` array) and handle `next_cursor` for pagination.

## Upgrade Command

To update your CLI tools to the latest version:

```bash
zrb upgrade --version 2.0.0
```
