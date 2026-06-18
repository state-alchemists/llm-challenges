# Migration Guide from Zrb v1 to v2

This guide provides a comprehensive overview of the breaking changes between Zrb v1 and v2, along with code examples to facilitate a smooth migration for developers.

## Breaking Changes

### 1. Endpoint Prefix Change
All API endpoints are now prefixed with `/v2/`.

#### Before:
```http
GET /tasks
```

#### After:
```http
GET /v2/tasks
```

---

### 2. Authentication Header Change
The authentication method has changed from using an API key in the header to a Bearer token.

#### Before:
```http
X-Auth-Token: <your_api_key>
```

#### After:
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
The `id` of a task has changed from an integer to a UUID string.

#### Before:
```json
{
  "id": 42,
  "title": "Write tests"
}
```

#### After:
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

---

### 4. Task Field Name Change
The field `done` has been renamed to `completed`.

#### Before:
```json
{
  "done": false
}
```

#### After:
```json
{
  "completed": false
}
```

---

### 5. Required Project ID for Task Creation
Task creation now requires a `project_id` field.

#### Before:
```json
{
  "title": "New task title"
}
```

#### After:
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Endpoints Return a Paginated Envelope
All list endpoints now return a paginated envelope rather than a bare array.

#### Before:
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

#### After:
```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false},
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567891", "title": "Ship v1", "completed": true}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Migration Checklist

1. Update all endpoint URLs to use the `/v2/` prefix.
2. Change API key usage in headers to Bearer token.
3. Update task ID handling from integer to UUID string.
4. Rename `done` field to `completed` in your task objects.
5. Ensure that task creation requests include the `project_id` field.
6. Adapt to the new paginated responses for list endpoints.

---

## Upgrade Command

To upgrade to Zrb v2, use the following command:
```bash
zrb upgrade
```