# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant improvements to project organization, pagination, and security. Because of these changes, v2 is not backward compatible with v1.

This guide will help you migrate your integration from the v1 API to the v2 API.

## Breaking Changes

### 1. API Versioning and Endpoints
All API endpoints now include a `/v2/` prefix.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
Authentication has moved from a custom header to the industry-standard Bearer token. Requests using the old header will now return `401 Unauthorized`.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type
Task IDs have been upgraded from integers to UUID strings to support better distributed scaling.

**v1**
```json
{ "id": 42 }
```

**v2**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" }
```

---

### 4. Renamed Completion Field
The `done` field has been renamed to `completed` for better clarity.

**v1**
```json
{ "done": false }
```

**v2**
```json
{ "completed": false }
```

---

### 5. Mandatory Project Association
Tasks can no longer exist in a vacuum. All new tasks must be associated with a project via a `project_id`. Omitting this field will result in a `422 Unprocessable Entity` error.

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

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope to improve performance for large datasets.

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

## Migration Checklist

- [ ] Update base URL for all API calls to include `/v2/`.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer`.
- [ ] Update data models to handle `id` as a string (UUID) instead of an integer.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Implement `project_id` logic for all task creation requests.
- [ ] Update list-handling logic to extract data from the `items` array and handle `next_cursor` pagination.

## Upgrade Command

To upgrade your CLI to the latest version:

```bash
zrb upgrade --to-v2
```
