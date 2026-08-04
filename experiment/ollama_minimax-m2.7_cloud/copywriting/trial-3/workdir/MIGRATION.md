# Zrb CLI Migration Guide: v1 → v2

v2 introduces projects, improved pagination, and stricter auth. This guide covers every breaking change and how to update your integration.

---

## Breaking Changes

### 1. URL Prefix Changed from `/tasks` to `/v2/tasks`

All endpoint paths now include the `/v2/` prefix.

| Endpoint | v1 | v2 |
|----------|----|----|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before:**
```http
GET /tasks
```

**After:**
```http
GET /v2/tasks
```

---

### 2. Authentication Header Changed

The auth header has changed from a custom header to a standard Bearer token.

| | v1 | v2 |
|-|----|----|
| Header | `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` |
| Failure response | — | HTTP 401 |

Requests with the v1 `X-Auth-Token` header will now be rejected with HTTP 401.

**Before:**
```http
X-Auth-Token: sk_live_abc123
```

**After:**
```http
Authorization: Bearer sk_live_abc123
```

---

### 3. Task `id` Type Changed from Integer to UUID String

Task IDs are no longer sequential integers — they are now UUID v4 strings.

| | v1 | v2 |
|-|----|----|
| `id` type | integer | string (UUID) |
| Example | `42` | `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

Any code that treats `id` as an integer (parsing, incrementing, database column type, etc.) will break.

**Before:**
```json
{
  "id": 42,
  "title": "Write tests"
}
```

**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

---

### 4. Task Field `done` Renamed to `completed`

The `done` boolean field has been renamed to `completed`.

| | v1 | v2 |
|-|----|----|
| Field name | `done` | `completed` |
| Type | boolean | boolean |
| Default | `false` | `false` |

Update all references in request bodies and response handling.

**Before:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task Creation Now Requires `project_id`

Creating a task now requires a `project_id` field. Omitting it returns HTTP 422.

| | v1 | v2 |
|-|----|----|
| `project_id` | not present | **required** |
| Missing field response | HTTP 201 | HTTP 422 |

You must provision at least one project before creating tasks. See your project dashboard or use `zrb project create`.

**Before:**
```json
{
  "title": "New task title"
}
```

**After:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Endpoints Return Paginated Envelope Instead of Bare Array

List responses are no longer bare arrays. They are wrapped in a pagination envelope.

| | v1 | v2 |
|-|----|----|
| Response shape | `[{...}, {...}]` | `{ "items": [...], "total": N, "next_cursor": "..." }` |
| Pagination | none | cursor-based |
| Query params | none | `cursor`, `limit` |

Update code that expects an array directly from list endpoints. Access items via `response.items`.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After:**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

To fetch the next page, pass `?cursor=<next_cursor>`.

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Change task `id` handling from integer to UUID string (database columns, types, serialization)
- [ ] Rename all occurrences of `done` to `completed` in request bodies and response parsing
- [ ] Add `project_id` to all task creation calls (obtain project IDs from your project dashboard)
- [ ] Update list response parsing to access `response.items` instead of the root array
- [ ] Implement cursor-based pagination for list endpoints if paginating through large task sets
- [ ] Update any database schemas or serialization logic that stores task IDs as integers
- [ ] Test against the v2 API before shipping

---

## Upgrade Command

```bash
npm install @zrb/cli@latest
```

Or, if using yarn:

```bash
yarn upgrade @zrb/cli@latest
```
