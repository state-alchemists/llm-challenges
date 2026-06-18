# Migrating to Zrb CLI v2

The Zrb CLI has been upgraded to v2. This release introduces a more robust data model with project support, improved pagination for large datasets, and a modernized authentication system.

Because these changes introduce breaking API modifications, developers using v1 must update their integration code to maintain functionality.

## Breaking Changes

### 1. API Versioning
All endpoints have been moved under the `/v2/` prefix.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
The custom `X-Auth-Token` header has been replaced by the industry-standard Bearer token.

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
Task `id`s have changed from integers to UUID strings to support better distributed scaling.

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

### 5. Project Requirement for Task Creation
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
List endpoints no longer return a bare array. They now return a paginated envelope to prevent timeouts and payload overflow.

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

- [ ] Update base URL/endpoints to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to handle UUID strings for task IDs instead of integers.
- [ ] Replace all occurrences of the `done` field with `completed` in request and response handling.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Refactor list-fetching logic to handle the paginated envelope and implement cursor-based navigation (`?cursor=...`).

## Upgrade Command

To update your CLI to the latest version, run:

```bash
zrb update --version 2.0.0
```
