# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including project-based task organization and enhanced pagination. These changes require updates to your API integration.

## Breaking Changes

### 1. API Versioning
All endpoints are now versioned. You must prefix your requests with `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication
Zrb has moved from a custom header to standard Bearer token authentication. Requests using the old header will return `401 Unauthorized`.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task IDs
Task identifiers have changed from integers to UUID strings to support distributed scaling.

**v1**
```json
{ "id": 42 }
```

**v2**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" }
```

### 4. Field Rename: `done` → `completed`
The `done` field in the Task object has been renamed to `completed` for better clarity.

**v1**
```json
{ "done": true }
```

**v2**
```json
{ "completed": true }
```

### 5. Mandatory Project Association
Tasks must now belong to a project. The `project_id` field is now required during task creation; omitting it will result in a `422 Unprocessable Entity` error.

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

### 6. Paginated Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

**v1**
```json
[
  { "id": 1, "title": "Task 1" },
  { "id": 2, "title": "Task 2" }
]
```

**v2**
```json
{
  "items": [
    { "id": "uuid-1", "title": "Task 1" },
    { "id": "uuid-2", "title": "Task 2" }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer`.
- [ ] Update data models to handle UUID strings for task IDs.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Ensure `project_id` is provided in all `POST /v2/tasks` requests.
- [ ] Update response parsing for list endpoints to handle the paginated envelope.

## Upgrade Command

To update your CLI to the latest version, run:

```bash
zrb update --version 2.0.0
```
