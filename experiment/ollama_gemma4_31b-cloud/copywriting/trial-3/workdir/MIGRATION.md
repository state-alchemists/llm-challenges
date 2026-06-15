# Migrating to Zrb CLI v2

Zrb v2 introduces several breaking changes to the Task API to support project-based organization, improved scalability via pagination, and modernized authentication. This guide will help you transition your integration from v1 to v2.

## Breaking Changes

### 1. Endpoint Versioning
All API endpoints are now prefixed with `/v2/`. Requests to v1 endpoints will no longer be supported.

**v1:** `GET /tasks`
**v2:** `GET /v2/tasks`

### 2. Authentication Header
Authentication has moved from a custom header to the industry-standard Bearer token.

**v1:**
```http
X-Auth-Token: <your_api_key>
```

**v2:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task Identifier Type
Task IDs have changed from integers to UUID strings. Update your database schemas and type definitions to accommodate strings.

**v1:**
```json
{ "id": 42 }
```

**v2:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" }
```

### 4. Field Rename: `done` $\rightarrow$ `completed`
The `done` boolean field has been renamed to `completed` for better clarity.

**v1:**
```json
{ "done": false }
```

**v2:**
```json
{ "completed": false }
```

### 5. Required `project_id` on Creation
Tasks must now belong to a project. The `project_id` field is now mandatory when creating a task. Omitting this field will result in an `HTTP 422 Unprocessable Entity` response.

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
List endpoints no longer return a bare array. They now return a paginated envelope. You must now access tasks via the `items` array and use `next_cursor` for pagination.

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
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] Update base URL to include `/v2/` prefix.
- [ ] Change authentication header from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update Task ID types from `Integer` to `String` (UUID).
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Ensure `project_id` is included in all `POST /v2/tasks` requests.
- [ ] Update list endpoint parsing to handle the paginated envelope (`items` array).
- [ ] Implement cursor-based pagination using `next_cursor`.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --version 2.0.0
```
