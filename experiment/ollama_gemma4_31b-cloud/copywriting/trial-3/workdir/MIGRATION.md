# Migrating to Zrb CLI v2

Zrb CLI v2 introduces several breaking changes to improve API scalability, security, and resource organization. This guide will help you migrate your existing v1 integrations to the v2 API.

## Breaking Changes

### 1. API Versioning
All API endpoints are now prefixed with `/v2/`. Requests sent to v1 endpoints will no longer be supported.

**v1 Example:**
`GET /tasks`

**v2 Example:**
`GET /v2/tasks`

---

### 2. Authentication Header
The authentication mechanism has moved from a custom header to a standard Bearer token. Requests using `X-Auth-Token` will now return an `HTTP 401 Unauthorized` response.

**v1 Before:**
```http
X-Auth-Token: <your_api_key>
```

**v2 After:**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Format
Task identifiers have changed from integers to UUID strings to prevent ID enumeration and support distributed scaling.

**v1 Before:**
```json
{
  "id": 42,
  "title": "Write tests"
}
```

**v2 After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

---

### 4. Field Rename: `done` $\rightarrow$ `completed`
To better align with industry standards, the `done` boolean field has been renamed to `completed`.

**v1 Before:**
```json
{
  "title": "Buy milk",
  "done": false
}
```

**v2 After:**
```json
{
  "title": "Buy milk",
  "completed": false
}
```

---

### 5. Mandatory Project Association
Tasks are now organized into projects. When creating a new task, a `project_id` is now **required**. Omitting this field will result in an `HTTP 422 Unprocessable Entity` response.

**v1 Before:**
```json
{
  "title": "New task title"
}
```

**v2 After:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Responses
List endpoints no longer return a bare array of objects. They now return a paginated envelope to handle larger datasets efficiently.

**v1 Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**v2 After:**
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
*To fetch the next page, pass the `next_cursor` value as a query parameter: `GET /v2/tasks?cursor=cursor_xyz`.*

---

## Migration Checklist

- [ ] Update all base URLs to include the `/v2/` prefix.
- [ ] Change authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Rename all references of the `done` field to `completed` in request and response bodies.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list endpoint handlers to parse the `items` array from the paginated envelope.
- [ ] Implement cursor-based pagination using the `next_cursor` field.

## Upgrade Command

To upgrade your CLI tools to the latest version:

```bash
zrb update --version 2.0.0
```
