# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant improvements to the Task API, including project-based organization, robust pagination, and industry-standard authentication. These changes are breaking and require updates to your integration.

## Breaking Changes

### 1. API Versioning
All API endpoints are now prefixed with `/v2/`. Requests made to v1 endpoints will no longer be supported.

**v1**
`GET /tasks`

**v2**
`GET /v2/tasks`

---

### 2. Authentication
Authentication has moved from a custom header to the standard Bearer token format.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task Identifiers
Task `id` values have changed from integers to UUID strings to ensure global uniqueness.

**v1**
```json
{ "id": 42, "title": "Write tests" }
```

**v2**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests" }
```

---

### 4. Task Status Field
The field `done` has been renamed to `completed` for better clarity.

**v1**
```json
{ "title": "Update docs", "done": true }
```

**v2**
```json
{ "title": "Update docs", "completed": true }
```

---

### 5. Required Project Association
Tasks must now be associated with a project. When creating a task, `project_id` is a required field.

**v1**
```json
{ "title": "New task" }
```

**v2**
```json
{ 
  "title": "New task", 
  "project_id": "proj_abc123" 
}
```

---

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

**v1**
```json
[
  { "id": 1, "title": "Task 1" },
  { "id": 2, "title": "Task 2" }
]
```

**v2**
```json
{
  "items": [
    { "id": "uuid-1", "title": "Task 1" },
    { "id": "uuid-2", "title": "Task 2" }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] Update data models to treat task `id` as a string (UUID) instead of an integer.
- [ ] Rename all references of the `done` field to `completed` in API requests and responses.
- [ ] Ensure all `POST /v2/tasks` requests include a valid `project_id`.
- [ ] Update list-handling logic to parse the `items` array from the paginated envelope.
- [ ] Implement cursor-based pagination using the `next_cursor` and `?cursor=` query parameter.

## Upgrade Command

To upgrade your CLI to the latest version, run:

```bash
zrb upgrade --version 2.0.0
```
