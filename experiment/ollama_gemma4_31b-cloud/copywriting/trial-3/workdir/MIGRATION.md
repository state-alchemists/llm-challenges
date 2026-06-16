# Migrating to Zrb CLI v2

Zrb v2 introduces significant improvements to project organization, pagination, and security. Because these changes affect the API contract, this is a breaking release.

## Breaking Changes

### 1. API Endpoint Prefixing
All endpoints now require the `/v2/` prefix. Requests to v1 endpoints will no longer be supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
We have moved from a custom header to the industry-standard Bearer token authentication.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
Task identifiers have changed from integers to UUID strings to support distributed scaling.

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

### 4. Task Status Field Rename
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

### 5. Mandatory Project Association
Tasks can no longer exist in a vacuum. All new tasks must be associated with a `project_id`.

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
List endpoints no longer return a bare array. They now return a paginated envelope to ensure performance as your data grows.

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

---

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer`.
- [ ] Update data models to handle `id` as a string (UUID) instead of an integer.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update `POST /v2/tasks` calls to include a valid `project_id`.
- [ ] Update list-handling logic to extract tasks from the `items` array and handle `next_cursor` for pagination.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb update --version 2.0.0
```
