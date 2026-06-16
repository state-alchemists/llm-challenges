# Migrating to Zrb CLI v2

Zrb CLI v2 introduces a more scalable architecture with support for projects, robust pagination, and improved security. Because of these improvements, v2 includes several breaking changes to the API and data models.

This guide will help you transition your integration from v1 to v2.

## Breaking Changes

### 1. API Versioning (URL Prefix)
All API endpoints have been moved under the `/v2/` namespace to allow for side-by-side versioning.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
We have moved from a custom header to the industry-standard Bearer token. Requests using the old header will now return `HTTP 401 Unauthorized`.

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
Task IDs have changed from sequential integers to UUID strings to prevent ID enumeration and support distributed systems.

**v1**
`{"id": 42, ...}`

**v2**
`{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", ...}`

---

### 4. Field Rename: `done` $\rightarrow$ `completed`
The `done` field has been renamed to `completed` for better clarity and consistency across the API.

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

### 5. Required Project Association
Tasks can no longer exist in a global namespace. Every task must now be associated with a project. When creating a task, `project_id` is now a required field.

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
*Note: Omitting `project_id` will return `HTTP 422 Unprocessable Entity`.*

---

### 6. Paginated List Responses
To improve performance for large datasets, list endpoints no longer return a bare array. They now return a paginated envelope.

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
*To fetch the next page, pass the cursor in your request: `GET /v2/tasks?cursor=cursor_xyz`.*

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Switch `X-Auth-Token` header to `Authorization: Bearer`.
- [ ] Update data models to handle UUID strings for Task IDs instead of integers.
- [ ] Rename `done` field references to `completed` in both requests and responses.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list endpoint handlers to parse the `items` envelope and handle `next_cursor` pagination.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb update --version 2.0.0
```
