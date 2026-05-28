# Migrating to Zrb CLI v2

Zrb v2 introduces significant improvements to project organization, API scalability through pagination, and enhanced security. Because these changes affect core data structures and authentication, this is a breaking release.

This guide will help you transition your integration from v1 to v2.

## Breaking Changes

### 1. API Endpoint Versioning
All endpoints are now versioned. You must prefix your request paths with `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
The authentication mechanism has moved from a custom header to the standard Bearer token format. Requests using the old header will return `HTTP 401 Unauthorized`.

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
Task IDs have changed from integers to UUID strings to support distributed scaling and prevent ID enumeration.

**v1**
`GET /tasks/42`

**v2**
`GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890`

---

### 4. Field Rename: `done` → `completed`
To better align with industry standards, the `done` boolean field has been renamed to `completed`. This affects both the response body and the request body for updates.

**v1**
```json
{ "id": 42, "done": true }
```

**v2**
```json
{ "id": "a1b2...", "completed": true }
```

---

### 5. Mandatory Project Association
Tasks can no longer exist in a global namespace. Every new task must now be associated with a project via a `project_id`. Omitting this field during creation will result in an `HTTP 422 Unprocessable Entity` error.

**v1**
```json
{ "title": "New task title" }
```

**v2**
```json
{ 
  "title": "New task title",
  "project_id": "proj_abc123" 
}
```

---

### 6. List Response Pagination
The `/tasks` endpoint no longer returns a bare array. It now returns a paginated envelope containing the items, the total count, and a cursor for the next page.

**v1**
```json
[
  { "id": 1, "title": "Buy milk", ... },
  { "id": 2, "title": "Ship v1", ... }
]
```

**v2**
```json
{
  "items": [
    { "id": "uuid-1", "title": "Buy milk", ... },
    { "id": "uuid-2", "title": "Ship v1", ... }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
*To fetch the next page, use `GET /v2/tasks?cursor=cursor_xyz`.*

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to treat Task IDs as strings (UUIDs) instead of integers.
- [ ] Rename all occurrences of the `done` field to `completed` in codebase and tests.
- [ ] Identify the `project_id` for tasks and update `POST /v2/tasks` payloads.
- [ ] Update list-fetching logic to handle the new paginated envelope and implement cursor-based navigation.

## Upgrade Command

Update your CLI to the latest version:

```bash
zrb update --version 2.0.0
```
