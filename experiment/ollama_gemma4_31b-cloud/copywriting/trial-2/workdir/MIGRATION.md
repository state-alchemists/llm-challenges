# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and organization. This guide will help you migrate your existing v1 integrations to the v2 API.

## Breaking Changes

### 1. API Endpoint Versioning
All API endpoints have been moved to a versioned path. You must now prefix all requests with `/v2/`.

**v1:**
`GET /tasks`

**v2:**
`GET /v2/tasks`

---

### 2. Authentication Header
Authentication has moved from a custom header to a standard Bearer token. Requests using `X-Auth-Token` will now return a `401 Unauthorized` response.

**v1:**
```http
X-Auth-Token: <your_api_key>
```

**v2:**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task Identifier Type
Task IDs have changed from integers to UUID strings to support better distributed systems.

**v1:**
```json
{
  "id": 42
}
```

**v2:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

### 4. Field Rename: `done` $\rightarrow$ `completed`
The boolean field indicating task completion has been renamed for clarity.

**v1:**
```json
{
  "done": true
}
```

**v2:**
```json
{
  "completed": true
}
```

---

### 5. Mandatory `project_id` for Creation
To improve task organization, all tasks must now be associated with a project. The `project_id` field is now required when creating a task. Omitting this will result in a `422 Unprocessable Entity` error.

**v1:**
```json
{
  "title": "New task title"
}
```

**v2:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Responses
List endpoints no longer return a bare array. Instead, they return a paginated envelope containing the items and a cursor for the next page.

**v1:**
```json
[
  {"id": 1, "title": "Buy milk", ...},
  {"id": 2, "title": "Ship v1", ...}
]
```

**v2:**
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

- [ ] Update all base URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to treat Task IDs as strings (UUIDs) instead of integers.
- [ ] Rename all occurrences of the `done` field to `completed` in requests and response handling.
- [ ] Ensure all `POST /v2/tasks` requests include a valid `project_id`.
- [ ] Update list response handling to extract data from the `items` array of the paginated envelope.
- [ ] Implement cursor-based pagination using `next_cursor` for large datasets.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --version v2
```
