# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including the introduction of projects and a more robust pagination system. Because these changes improve long-term stability and scalability, they include several breaking changes to the API.

This guide will help you migrate your integration from v1 to v2.

## Breaking Changes

### 1. API Endpoint Prefixing
All endpoints now require the `/v2/` prefix to ensure version stability.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

### 2. Authentication Header
Authentication has moved from a custom header to the industry-standard Bearer token format.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
Task IDs have changed from integers to UUID strings. Update your data models and database schemas to support string-based identifiers.

**v1**
```json
{ "id": 42 }
```

**v2**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" }
```

### 4. Field Rename: `done` → `completed`
To improve clarity, the boolean field `done` has been renamed to `completed` across all task objects.

**v1**
```json
{ "done": false }
```

**v2**
```json
{ "completed": false }
```

### 5. Required Project Association
Tasks can no longer exist without a project. You must now provide a `project_id` when creating a task.

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

### 6. Paginated Response Envelopes
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and navigation metadata.

**v1**
```json
[
  { "id": 1, "title": "Buy milk" },
  { "id": 2, "title": "Ship v1" }
]
```

**v2**
```json
{
  "items": [
    { "id": "...", "title": "Buy milk" },
    { "id": "...", "title": "Ship v1" }
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

- [ ] Update all request URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data types for `id` from `integer` to `string` (UUID).
- [ ] Rename all instances of the `done` field to `completed` in requests and responses.
- [ ] Ensure `project_id` is passed during task creation.
- [ ] Update list-endpoint parsing logic to handle the paginated envelope (`items` array).
- [ ] Implement cursor-based pagination using the `next_cursor` and `?cursor=` parameter.

## Upgrade Command

Update your CLI to the latest version:

```bash
zrb update --version v2
```
