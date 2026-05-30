# Migrating to Zrb CLI v2

Zrb CLI v2 introduces architectural improvements, including project-based organization and standardized pagination. Because these changes alter the core API contract, this is a breaking release.

This guide will help you migrate your existing v1 integrations to v2.

## Breaking Changes

### 1. API Endpoint Prefixing
All endpoints have moved under the `/v2/` namespace.

**v1:**
`GET /tasks`

**v2:**
`GET /v2/tasks`

---

### 2. Authentication Header
The authentication scheme has shifted from a custom header to the industry-standard Bearer token.

**v1:**
```http
X-Auth-Token: <your_api_key>
```

**v2:**
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
Task IDs have changed from integers to UUID strings to support distributed scaling.

**v1:**
```json
{ "id": 42 }
```

**v2:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890" }
```

---

### 4. Property Rename: `done` → `completed`
The `done` boolean field has been renamed to `completed` for better clarity.

**v1:**
```json
{ "done": true }
```

**v2:**
```json
{ "completed": true }
```

---

### 5. Required `project_id` for Task Creation
Tasks must now be associated with a project. Providing a `project_id` is mandatory during creation.

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

---

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope to improve performance with large datasets.

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
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all API base URLs to include the `/v2/` prefix.
- [ ] Update authentication logic to use the `Authorization: Bearer` header.
- [ ] Update data models to treat Task IDs as strings (UUIDs) instead of integers.
- [ ] Rename all occurrences of the `done` property to `completed` in requests and responses.
- [ ] Update task creation logic to include a valid `project_id`.
- [ ] Refactor list-handling code to extract arrays from the `items` field of the response envelope.
- [ ] (Optional) Implement cursor-based pagination using the `next_cursor` field.

## Upgrade Command

Update your CLI to the latest version:

```bash
npm install -g zrb-cli@latest
```
