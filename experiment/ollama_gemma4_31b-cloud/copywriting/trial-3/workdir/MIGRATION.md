# Migrating to Zrb CLI v2

Zrb v2 introduces several architectural improvements, including project-based task organization, standardized pagination, and enhanced security. Because these changes modify the core API contract, this is a breaking release.

## Breaking Changes

### 1. API Versioning & Endpoints
All API endpoints are now versioned. You must prefix your requests with `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
The custom `X-Auth-Token` header has been deprecated in favor of the industry-standard `Authorization: Bearer` scheme.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task Identifier Type
Task IDs have migrated from auto-incrementing integers to UUID strings to support distributed scaling and better data integrity.

**v1**
`{"id": 42, ...}`

**v2**
`{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", ...}`

### 4. Task Status Field Rename
The `done` field has been renamed to `completed` to more accurately reflect the task state.

**v1**
`{"done": true}`

**v2**
`{"completed": true}`

### 5. Required Project Association
v2 introduces Projects. Every task must now belong to a project. The `project_id` field is now required during task creation.

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
  {"id": 1, "title": "Buy milk", ...},
  {"id": 2, "title": "Ship v1", ...}
]
```

**v2**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", ...},
    {"id": "...", "title": "Ship v1", ...}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] Update all base URLs to include the `/v2/` prefix.
- [ ] Switch authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to treat `id` as a string (UUID) instead of an integer.
- [ ] Rename all references of the task field `done` to `completed`.
- [ ] Ensure all `POST /v2/tasks` calls include a valid `project_id`.
- [ ] Update list-handling logic to read from the `.items` array and handle `next_cursor` for pagination.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb update --version v2
```
