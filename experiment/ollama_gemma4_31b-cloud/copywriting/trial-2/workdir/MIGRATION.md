# Migrating to Zrb CLI v2

Zrb v2 introduces several architectural improvements, including project-based organization, improved pagination, and a more secure authentication scheme. Because these changes alter the API surface, this is a breaking release.

This guide will walk you through the necessary changes to migrate your integration from v1 to v2.

## Breaking Changes

### 1. Endpoint Path Prefix
All API endpoints are now prefixed with `/v2/`. Requests to v1 paths will no longer be supported.

**Before (v1):**
`GET /tasks`

**After (v2):**
`GET /v2/tasks`

---

### 2. Authentication Header
Authentication has moved from a custom token header to the industry-standard Bearer token.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task Identification (ID Type)
Task IDs have transitioned from integers to UUID strings to support distributed scaling and better uniqueness.

**Before (v1):**
```json
{ "id": 42, "title": "Write tests" }
```

**After (v2):**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests" }
```

---

### 4. Field Rename: `done` $\rightarrow$ `completed`
To more accurately reflect task states, the `done` boolean field has been renamed to `completed`.

**Before (v1):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required `project_id` for Creation
Tasks must now belong to a project. The `project_id` field is now mandatory when creating a new task.

**Before (v1):**
```json
{
  "title": "New task title"
}
```

**After (v2):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Responses
List endpoints no longer return a bare array of objects. They now return a paginated envelope containing metadata and the items array.

**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**After (v2):**
```json
{
  "items": [
    {"id": "...", "title": "Buy milk", "completed": false},
    {"id": "...", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
*Tip: Use the `?cursor=cursor_xyz` query parameter to fetch subsequent pages.*

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Change authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to handle `id` as a string (UUID) instead of an integer.
- [ ] Rename all references of the `done` field to `completed` in your requests and response parsing.
- [ ] Update Task creation logic to include a valid `project_id`.
- [ ] Update List endpoint logic to parse the `items` array from the new paginated envelope.

## Upgrade Command

To upgrade your CLI to the latest version:

```bash
zrb upgrade --version v2
```
