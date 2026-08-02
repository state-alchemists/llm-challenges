# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including project-based organization and improved pagination. Because of these changes, v2 is not backward compatible with v1.

This guide will help you migrate your integration from v1 to v2.

## Breaking Changes

### 1. API Versioning & Endpoints
All API endpoints now require the `/v2/` prefix.

**v1:**
`GET /tasks`

**v2:**
`GET /v2/tasks`

### 2. Authentication Header
Authentication has moved from a custom token header to a standard Bearer token.

**v1:**
```http
X-Auth-Token: <your_api_key>
```

**v2:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
Task IDs have changed from integers to UUID strings to support distributed scaling.

**v1:**
```json
{
  "id": 42,
  "title": "Write tests"
}
```

**v2:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. Field Rename: `done` → `completed`
The boolean field indicating task completion has been renamed for clarity.

**v1:**
```json
{
  "title": "Write tests",
  "done": false
}
```

**v2:**
```json
{
  "title": "Write tests",
  "completed": false
}
```

### 5. Mandatory Project Association
All tasks must now belong to a project. The `project_id` field is now required during task creation.

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

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

**v1:**
```json
[
  {"id": 1, "title": "Buy milk", "completed": false},
  {"id": 2, "title": "Ship v1", "completed": true}
]
```

**v2:**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false},
    {"id": "uuid-2", "title": "Ship v1", "completed": true}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API endpoint URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Rename `done` fields to `completed` in all request and response handlers.
- [ ] Add `project_id` to all task creation requests.
- [ ] Update list-fetching logic to parse the `.items` array and handle `next_cursor` for pagination.

## Upgrade Command

Run the following command to update your CLI to the latest version:

```bash
zrb upgrade --version v2
```
