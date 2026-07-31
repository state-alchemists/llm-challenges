# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including project-based organization, robust pagination, and enhanced security. Because these changes impact the core API structure, this version contains breaking changes.

This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Endpoint Prefixing
All endpoints have been versioned. You must prefix all request paths with `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
Zrb has moved from a custom token header to the industry-standard Bearer token authentication. Requests using the old header will return `401 Unauthorized`.

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
Task IDs have migrated from sequential integers to UUID strings to support better distribution and security.

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
The boolean flag indicating task completion has been renamed for clarity.

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

### 5. Required `project_id` on Creation
Tasks must now belong to a project. The `project_id` field is now mandatory when creating a task. Omitting this field will result in a `422 Unprocessable Entity` error.

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
List endpoints no longer return a bare array. They now return a paginated envelope to ensure stability as your data grows.

**v1**
```json
[
  {"id": 1, "title": "Buy milk", ...},
  {"id": 2, "title": "Ship v1", ...}
]
```

**v2**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", ...},
    {"id": "uuid-2", "title": "Ship v1", ...}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-fetching logic to wrap results in the new paginated envelope and implement cursor-based pagination.

## Upgrade Command

To update your CLI to the latest version, run:

```bash
zrb update --version v2
```
