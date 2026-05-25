# Migrating to Zrb CLI v2

The Zrb CLI has been updated to v2. This release introduces a more scalable architecture with project grouping, robust pagination, and standard authentication. Because these changes affect the fundamental API structure, this is a **breaking release**.

## Breaking Changes

### 1. API Endpoint Prefixing
All API endpoints are now versioned. You must prefix your request paths with `/v2/`.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication Header
We have moved from a custom header to the industry-standard Bearer token authentication. Requests using the old header will now return `401 Unauthorized`.

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
Task IDs have changed from integers to UUID strings to prevent collisions and improve security in distributed environments.

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

### 4. Field Rename: `done` $\rightarrow$ `completed`
To better align with our internal state machine, the `done` boolean has been renamed to `completed`.

**v1**
```json
{
  "title": "Write tests",
  "done": false
}
```

**v2**
```json
{
  "title": "Write tests",
  "completed": false
}
```

---

### 5. Project Requirement for Task Creation
Tasks can no longer exist in a global namespace. When creating a task, a `project_id` is now mandatory. Requests missing this field will return `422 Unprocessable Entity`.

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
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

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
    {"id": "...", "title": "Buy milk", ...},
    {"id": "...", "title": "Ship v1", ...}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all request URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Update all references of the `done` field to `completed`.
- [ ] Ensure all `POST /v2/tasks` calls include a valid `project_id`.
- [ ] Update list-handling logic to parse the `items` array from the new paginated envelope.

## Upgrade Command

Update your CLI to the latest version using the following command:

```bash
zrb update --version v2
```
