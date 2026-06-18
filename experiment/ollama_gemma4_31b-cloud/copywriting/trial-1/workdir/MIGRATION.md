# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and organization. This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Versioning (Endpoint Prefix)
All API endpoints now require a `/v2/` prefix. Requests sent to v1 endpoints will be deprecated.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
The authentication mechanism has moved from a custom header to the standard Bearer token format.

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
Task IDs have changed from integers to UUID strings to prevent ID enumeration and support distributed systems.

**v1**
```json
{ "id": 42 }
```

**v2**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" }
```

---

### 4. Field Rename: `done` → `completed`
The boolean field indicating task status has been renamed for clarity.

**v1**
```json
{ "done": false }
```

**v2**
```json
{ "completed": false }
```

---

### 5. Project Association Required
Tasks must now be associated with a project. The `project_id` field is now required during task creation.

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
List endpoints no longer return a bare array. They now return a paginated envelope to handle large datasets efficiently.

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
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer` tokens.
- [ ] Update data models to treat `id` as a string instead of an integer.
- [ ] Rename all occurrences of the `done` field to `completed` in request and response bodies.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Refactor list-fetching logic to handle the new paginated envelope and use the `next_cursor` for subsequent pages.

## Upgrade Command

To update your Zrb CLI to the latest version, run:

```bash
zrb update --version v2
```
