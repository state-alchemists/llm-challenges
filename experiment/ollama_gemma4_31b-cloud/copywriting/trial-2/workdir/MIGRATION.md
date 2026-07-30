# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve scalability, security, and organization. This guide will help you migrate your existing v1 integrations to the new API.

## Breaking Changes

### 1. API Versioning & Endpoints
All API endpoints are now prefixed with `/v2/`. Requests to v1 endpoints will no longer be supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication
The authentication header has changed from a custom token to a standard Bearer token. Requests using the old header will receive an `HTTP 401 Unauthorized` response.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task Identity (ID Type)
Task IDs have transitioned from integers to UUID strings to support distributed data across projects.

**v1**
```json
{
  "id": 42,
  "title": "Write tests"
}
```

**v2**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

---

### 4. Renamed Completion Field
The `done` field has been renamed to `completed` for better clarity.

**v1**
```json
{
  "title": "Write tests",
  "done": true
}
```

**v2**
```json
{
  "title": "Write tests",
  "completed": true
}
```

---

### 5. Required Project Context
Task creation now requires a `project_id`. Omitting this field will result in an `HTTP 422 Unprocessable Entity` response.

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
List endpoints no longer return a bare array. They now return a paginated envelope containing the items, the total count, and a cursor for the next page.

**v1**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**v2**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false},
    {"id": "uuid-2", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update base URL/endpoints to include the `/v2/` prefix.
- [ ] Update authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to handle UUID strings instead of integers for `id`.
- [ ] Replace all references to the `done` field with `completed`.
- [ ] Update `POST /v2/tasks` requests to include a valid `project_id`.
- [ ] Update list response parsing to extract data from the `items` array in the new envelope.
- [ ] Implement cursor-based pagination using `?cursor=<next_cursor>`.

## Upgrade Command

Update your CLI to the latest version:

```bash
zrb update --version v2
```
