# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, organization, and security. This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Versioning
All endpoints are now prefixed with `/v2/`. Requests made to v1 endpoints will no longer be supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

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

---

### 3. Task ID Type
Task IDs have changed from integers to UUID strings to support distributed systems and prevent ID enumeration.

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
The `done` field has been renamed to `completed` for better clarity.

**v1**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**v2**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

---

### 5. Required `project_id` on Creation
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
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for further requests.

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
    {"id": "uuid-1", "title": "Buy milk", "completed": false, "project_id": "p1"},
    {"id": "uuid-2", "title": "Ship v1", "completed": true, "project_id": "p1"}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API endpoint URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to treat `id` as a string (UUID) instead of an integer.
- [ ] Rename all occurrences of the `done` field to `completed` in requests and responses.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list response handling to extract data from the `items` array in the paginated envelope.
- [ ] Implement cursor-based pagination using the `next_cursor` and `?cursor=` parameter.

## Upgrade Command

Run the following command to upgrade your CLI to the latest version:

```bash
zrb upgrade --version v2
```
