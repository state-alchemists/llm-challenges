# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve security, scalability, and organization. This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Endpoint Prefixing
All v2 endpoints are now prefixed with `/v2/`. Requests to v1 endpoints (without the prefix) are no longer supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
Authentication has moved from a custom header to the industry-standard Bearer token format. Requests using `X-Auth-Token` will now return `HTTP 401 Unauthorized`.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Format
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

### 4. Task Completion Field
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

### 5. Required Project ID
Tasks are now associated with projects. When creating a task, a `project_id` is now mandatory. Omitting this field will result in an `HTTP 422 Unprocessable Entity` response.

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
*To fetch the next page, pass the `next_cursor` value as a query parameter: `GET /v2/tasks?cursor=cursor_xyz`.*

## Migration Checklist

- [ ] Update base URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use `Authorization: Bearer <token>`.
- [ ] Update data models to handle UUID strings for Task IDs instead of integers.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list response handling to extract data from the `items` array within the pagination envelope.
- [ ] Implement cursor-based pagination for large task lists.

## Upgrade Command

To upgrade your local CLI to v2, run:

```bash
zrb update --version 2.0.0
```
