# Migrating to Zrb CLI v2

Welcome to the Zrb CLI v2 migration guide. v2 introduces projects, improved pagination, and stricter authentication to provide a more scalable experience.

Because v2 includes several breaking changes to the API and data models, you will need to update your integration code to maintain functionality.

## Breaking Changes

### 1. API Endpoint Prefixing
All API endpoints have been moved under the `/v2/` namespace to allow for side-by-side versioning.

**Before (v1):**
```bash
curl https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl https://api.zrb.io/v2/tasks
```

---

### 2. Authentication Header
The authentication method has shifted from a custom header to the industry-standard Bearer token.

**Before (v1):**
```http
X-Auth-Token: <your_api_key>
```

**After (v2):**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
Task IDs have been upgraded from integers to UUID strings to prevent collisions across distributed systems.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests"
}
```

**After (v2):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

---

### 4. Task Status Field Rename
The `done` field has been renamed to `completed` for better clarity.

**Before (v1):**
```json
{
  "title": "Update docs",
  "done": true
}
```

**After (v2):**
```json
{
  "title": "Update docs",
  "completed": true
}
```

---

### 5. Required Project ID for Creation
Tasks must now be associated with a project. The `project_id` field is now required when creating a task.

**Before (v1):**
```json
{
  "title": "New task title"
}
```

**After (v2):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope containing the items and a cursor for the next page.

**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "completed": false},
  {"id": 2, "title": "Ship v1", "completed": true}
]
```

**After (v2):**
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

- [ ] Update all base URLs to include the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` headers with `Authorization: Bearer`.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Rename all references of the `done` field to `completed`.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Update list-handling logic to parse the new paginated envelope (`items` array) instead of a direct array.

## Upgrade Command

To upgrade your Zrb CLI to the latest version, run:

```bash
zrb upgrade --version v2
```
