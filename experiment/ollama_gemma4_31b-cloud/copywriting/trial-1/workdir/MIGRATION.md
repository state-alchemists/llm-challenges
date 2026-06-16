# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve security, scalability, and data organization. This guide will help you migrate your existing v1 integrations to the v2 API.

## Breaking Changes

### 1. API Endpoint Prefix
All API endpoints are now versioned. You must prefix all your request paths with `/v2/`.

**v1:** `GET /tasks`
**v2:** `GET /v2/tasks`

### 2. Authentication Header
We have moved from a custom header to the industry-standard Bearer token authentication. Requests using the old header will now return `401 Unauthorized`.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
Task IDs have changed from integers to UUID strings to prevent ID enumeration and improve distributed system reliability.

**v1**
```json
{ "id": 42 }
```

**v2**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" }
```

### 4. Field Rename: `done` → `completed`
The `done` field has been renamed to `completed` for better clarity. This affects both the response objects and the request bodies for updates.

**v1**
```json
{ "done": true }
```

**v2**
```json
{ "completed": true }
```

### 5. Mandatory `project_id` for Task Creation
Tasks can no longer be created without being associated with a project. You must now provide a `project_id` when creating a task, otherwise the API will return `422 Unprocessable Entity`.

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

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

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
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use `Authorization: Bearer <token>`.
- [ ] Update data models to treat `id` as a string (UUID) instead of an integer.
- [ ] Rename all occurrences of the `done` field to `completed` in your code and API requests.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list response handling to extract tasks from the `items` array and implement cursor-based pagination if necessary.

## Upgrade Command

To upgrade your local CLI to the latest version, run:

```bash
zrb update --version v2
```
