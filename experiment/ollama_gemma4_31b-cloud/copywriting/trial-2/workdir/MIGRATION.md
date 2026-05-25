# Migrating to Zrb CLI v2

Zrb CLI v2 introduces systemic improvements to authentication, data modeling, and scalability. Because these changes improve the core architecture, v2 is not backward compatible with v1.

This guide will walk you through the breaking changes and the steps required to update your integration.

## Breaking Changes

### 1. API Endpoint Prefixing
All API endpoints have been versioned. You must prefix your request paths with `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Method
The authentication header has moved from a custom token to the industry-standard Bearer token format.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task Identification (ID Type)
Task IDs have changed from integers to UUID strings to support better distributed scaling. Update your database schemas and type definitions to handle strings.

**v1**
```json
{
  "id": 42
}
```

**v2**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

### 4. Task Status Field Rename
The `done` boolean has been renamed to `completed` for better clarity.

**v1**
```json
{
  "done": false
}
```

**v2**
```json
{
  "completed": false
}
```

---

### 5. Mandatory Project Association
Tasks are now required to belong to a project. When creating a task, you must provide a `project_id`. Omitting this field will result in an `HTTP 422 Unprocessable Entity` response.

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
List endpoints no longer return a bare array. They now return a paginated envelope containing the items, the total count, and a cursor for the next page.

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
    {"id": "...", "title": "Buy milk", ...},
    {"id": "...", "title": "Ship v1", ...}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
*To fetch the next page in v2, append `?cursor=cursor_xyz` to your request.*

## Migration Checklist

- [ ] **Update Base URLs**: Prefix all task-related endpoints with `/v2/`.
- [ ] **Update Auth Headers**: Switch from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] **Update Type Definitions**: Change Task `id` from `Integer` to `String` (UUID).
- [ ] **Update Field References**: Rename all instances of `done` to `completed`.
- [ ] **Implement Project IDs**: Ensure `project_id` is passed during task creation.
- [ ] **Update List Parsing**: Update logic to extract tasks from the `items` array in the paginated response.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb update --version 2.0.0
```
