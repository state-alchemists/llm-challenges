# Migrating to Zrb CLI v2

Zrb CLI v2 introduces structural changes to improve scalability, including the introduction of projects and a standardized pagination model. Because of these changes, v2 is not backward compatible with v1.

This guide will help you migrate your existing integrations from v1 to v2.

## Breaking Changes

### 1. API Versioning
All endpoints now require a `/v2/` prefix.

**v1**
```bash
curl https://api.zrb.io/tasks
```

**v2**
```bash
curl https://api.zrb.io/v2/tasks
```

### 2. Authentication Header
The authentication header has moved from a custom token header to a standard Bearer token.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type
Task IDs have transitioned from integers to UUID strings to support distributed scaling.

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

### 4. Field Rename: `done` → `completed`
The `done` boolean field has been renamed to `completed` for clarity.

**v1**
```json
{
  "done": true
}
```

**v2**
```json
{
  "completed": true
}
```

### 5. Required `project_id` on Creation
Tasks can no longer be created without being associated with a project. The `project_id` field is now required in the request body.

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
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for subsequent requests.

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

---

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Change `X-Auth-Token` headers to `Authorization: Bearer <token>`.
- [ ] Update data models to treat `id` as a string (UUID) instead of an integer.
- [ ] Replace all references to the `done` field with `completed`.
- [ ] Ensure `project_id` is passed when calling the Create Task endpoint.
- [ ] Update list-handling logic to parse the `items` array from the paginated envelope.
- [ ] Implement cursor-based pagination using the `next_cursor` field.

## Upgrade Command

To update your CLI tool to the latest version, run:

```bash
zrb upgrade --version v2
```
