# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and data organization. This guide will help you transition your integration from v1 to v2.

## Breaking Changes

### 1. Endpoint Prefixing
All API endpoints have been versioned. You must now prefix your request paths with `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
We have moved from a custom auth token to the industry-standard Bearer token format.

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
Task IDs have changed from integers to UUID strings to prevent ID enumeration and improve distributed system reliability.

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

### 4. Field Rename: `done` $\rightarrow$ `completed`
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

### 5. Required `project_id` for Task Creation
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
    {"id": "uuid-1", "title": "Buy milk", "completed": false},
    {"id": "uuid-2", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update base URL or append `/v2/` to all task endpoints.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to handle `id` as a string (UUID) instead of an integer.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list response handling to extract tasks from the `items` array in the new envelope.
- [ ] Implement cursor-based pagination for large task lists.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb update --version v2
```
