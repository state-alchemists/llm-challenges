# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant improvements to API structure, security, and data modeling. Because these changes impact core request/response patterns and data types, this is a breaking release.

This guide provides the necessary steps to migrate your integration from v1 to v2.

## Breaking Changes

### 1. Endpoint Prefixing
All API endpoints now require the `/v2/` prefix. Requests made to v1 endpoints will no longer be supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Method
Authentication has moved from a custom header to the industry-standard Bearer token. Requests using the old header will return `401 Unauthorized`.

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
Task identifiers have changed from integers to UUID strings to support distributed scaling and prevent ID enumeration.

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

### 4. Task Status Field Renamed
The field used to track task completion has been renamed from `done` to `completed` for better clarity.

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
Tasks must now belong to a project. When creating a task, the `project_id` field is now required. Omitting this field will result in an `HTTP 422 Unprocessable Entity` error.

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

### 6. Paginated Response Envelopes
List endpoints no longer return a bare array. They now return a paginated envelope containing metadata and a cursor for fetching subsequent pages.

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

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Switch authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to handle `id` as a string instead of an integer.
- [ ] Replace all references to the `done` field with `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list response handlers to extract data from the `.items` array.
- [ ] Implement cursor-based pagination using the `next_cursor` field and `?cursor=` query parameter.

## Upgrade Command

To update your CLI to the latest version:

```bash
zrb update --version v2
```
