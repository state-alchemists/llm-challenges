# Migrating to Zrb CLI v2

Zrb CLI v2 introduces structural changes to improve scalability, specifically regarding project organization and data pagination. This guide will help you migrate your integration from v1 to v2.

## Breaking Changes

### 1. API Endpoint Prefixing
All endpoints have been moved under the `/v2/` namespace to allow for side-by-side versioning.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
Authentication has moved from a custom header to the industry-standard Bearer token format. Requests using `X-Auth-Token` will now return `401 Unauthorized`.

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
Task identifiers have transitioned from integers to UUID strings to prevent ID exhaustion and improve distributed uniqueness.

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

### 4. Field Rename: `done` → `completed`
The `done` field has been renamed to `completed` for better clarity.

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

### 5. Required `project_id` for Task Creation
Tasks must now be associated with a project. Providing a `project_id` is mandatory when creating a task; omitting it will result in a `422 Unprocessable Entity` error.

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
List endpoints no longer return a bare array. Instead, they return a paginated envelope containing the items and a cursor for the next page.

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
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to handle `id` as a string (UUID) instead of an integer.
- [ ] Replace all references to the `done` field with `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Refactor list response handling to extract tasks from the `items` array and implement cursor-based pagination.

## Upgrade Command

To update your CLI to the latest version, run:

```bash
zrb update --version 2.0.0
```
