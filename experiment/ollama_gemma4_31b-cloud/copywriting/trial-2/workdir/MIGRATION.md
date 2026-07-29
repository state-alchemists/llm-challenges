# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and organization. This guide will help you migrate your integrations from v1 to v2.

## Breaking Changes

### 1. API Endpoint Prefixing
All API endpoints are now prefixed with `/v2/`. 

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
The authentication mechanism has moved from a custom header to a standard Bearer token. Requests using the old header will return `401 Unauthorized`.

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
Task identifiers have changed from integers to UUID strings to prevent ID enumeration and support distributed generation.

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
The field used to track task completion has been renamed for clarity.

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

### 5. Required Project Association
Tasks must now belong to a project. The `project_id` field is required during task creation. Omitting this field will result in a `422 Unprocessable Entity` error.

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
  {"id": 1, "title": "Buy milk"},
  {"id": 2, "title": "Ship v1"}
]
```

**v2**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk"},
    {"id": "...", "title": "Ship v1"}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
*To fetch the next page, append `?cursor=cursor_xyz` to your request.*

## Migration Checklist

- [ ] Update all base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer` tokens.
- [ ] Update data models to handle UUID strings for task IDs instead of integers.
- [ ] Rename all occurrences of the `done` field to `completed` in request and response bodies.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-fetching logic to wrap responses in the paginated envelope and handle `next_cursor` for pagination.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb update --version 2.0.0
```
