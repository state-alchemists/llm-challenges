# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve API consistency, scalability, and security. This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Endpoint Versioning
All endpoints are now prefixed with `/v2/`. Any requests sent to v1 endpoints will either be deprecated or return errors.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
Authentication has moved from a custom header to the standard Bearer token format.

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
Task IDs have transitioned from integers to UUID strings to support distributed scaling.

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
The boolean field `done` has been renamed to `completed` for better clarity.

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

### 5. Required `project_id` for Task Creation
Tasks must now be associated with a project. Providing a `project_id` is mandatory when creating tasks.

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

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Rename all occurrences of the `done` field to `completed` in request and response handlers.
- [ ] Ensure `project_id` is passed during task creation.
- [ ] Update list-fetching logic to parse the paginated envelope (`items` array) and handle `next_cursor` for pagination.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --version v2
```
