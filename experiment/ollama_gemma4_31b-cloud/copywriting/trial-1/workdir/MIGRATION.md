# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and data organization. This guide will help you migrate your existing v1 integrations to the new v2 API.

## Breaking Changes

### 1. API Endpoint Prefixing
All API endpoints have been versioned. You must prepend `/v2/` to all your request paths.

**v1 (Old)**
`GET /tasks`

**v2 (New)**
`GET /v2/tasks`

### 2. Authentication Header
The authentication mechanism has shifted from a custom header to the industry-standard Bearer token.

**v1 (Old)**
```http
X-Auth-Token: <your_api_key>
```

**v2 (New)**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
Task IDs have migrated from integers to UUID strings to prevent ID enumeration and support distributed systems.

**v1 (Old)**
`42`

**v2 (New)**
`"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`

### 4. Field Rename: `done` $\rightarrow$ `completed`
The `done` boolean field in Task objects has been renamed to `completed` for better clarity.

**v1 (Old)**
```json
{
  "id": 42,
  "done": false
}
```

**v2 (New)**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "completed": false
}
```

### 5. Mandatory `project_id` for Task Creation
Tasks must now be associated with a project. The `project_id` field is now required when creating a task. Omitting this field will result in an `HTTP 422 Unprocessable Entity` response.

**v1 (Old)**
```json
{
  "title": "New task title"
}
```

**v2 (New)**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope to handle larger datasets efficiently.

**v1 (Old)**
```json
[
  {"id": 1, "title": "Buy milk", ...},
  {"id": 2, "title": "Ship v1", ...}
]
```

**v2 (New)**
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
*To fetch the next page, pass the `next_cursor` value as a query parameter: `?cursor=cursor_xyz`.*

---

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Change the authentication header from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to handle `id` as a string (UUID) instead of an integer.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-handling logic to parse the `items` array within the paginated envelope.
- [ ] Implement cursor-based pagination for list endpoints if applicable.

## Upgrade Command

To update your CLI to the latest version, run:

```bash
zrb update --version v2
```
