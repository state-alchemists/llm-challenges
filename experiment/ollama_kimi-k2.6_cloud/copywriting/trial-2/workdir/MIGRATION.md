# Migrating from Zrb v1 to v2

Zrb v2 adds projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change you need to address when upgrading an existing v1 integration.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every task endpoint moved under the `/v2/` namespace.

**Before (v1)**
```bash
curl -H "X-Auth-Token: $TOKEN" \
  https://api.zrb.io/tasks
```

**After (v2)**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.zrb.io/v2/tasks
```

---

### 2. Authentication header changed from `X-Auth-Token` to Bearer token

The custom `X-Auth-Token` header is removed. Send an `Authorization: Bearer` header instead. Requests using the old header now receive HTTP 401.

**Before (v1)**
```bash
curl -H "X-Auth-Token: $API_KEY" \
  https://api.zrb.io/tasks/42
```

**After (v2)**
```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings. Update any client-side models, databases, or URL formatting that assumed an integer ID.

**Before (v1)**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2)**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 4. Task field `done` renamed to `completed`

The boolean status field is now called `completed`. Update any serialization, deserialization, or filtering logic that references `done`.

**Before (v1)**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2)**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` returns HTTP 422.

**Before (v1)**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: $TOKEN" \
  -d '{"title":"New task title"}'
```

**After (v2)**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"New task title","project_id":"proj_abc123"}'
```

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a top-level JSON array. It returns an envelope containing `items`, `total`, and `next_cursor`. Pass `?cursor=<next_cursor>` to walk pages.

**Before (v1)**
```bash
curl -H "X-Auth-Token: $TOKEN" \
  https://api.zrb.io/tasks
```

**Response**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "2024-01-15T10:30:00Z"},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "2024-01-15T11:00:00Z"}
]
```

**After (v2)**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.zrb.io/v2/tasks?limit=20"
```

**Response**
```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"},
    {"id": "b2c3d4e5-f6a7-8901-bcde-f12345678901", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "2024-01-15T11:00:00Z"}
  ],
  "total": 2,
  "next_cursor": null
}
```

---

## Step-by-Step Migration Checklist

Use this checklist to upgrade a production integration without skipping a breaking change.

- [ ] **Install the v2 package**
  ```bash
  npm install zrb@2
  ```
- [ ] **Update base URL references** to include the `/v2/` prefix on every endpoint.
- [ ] **Replace authentication headers** — swap `X-Auth-Token` for `Authorization: Bearer <token>` in all requests.
- [ ] **Migrate task ID storage** from integer to UUID string in local models, caches, and databases.
- [ ] **Rename `done` to `completed`** in request bodies, response parsing, and any UI bindings.
- [ ] **Add `project_id` to all task creation calls** and validate the value before sending.
- [ ] **Refactor list-task consumers** to read `response.items` instead of the top-level array.
- [ ] **Implement cursor pagination** using `?cursor=<next_cursor>` when iterating over large task lists.
- [ ] **Run your full test suite** against the v2 endpoints and fix any 401/404/422 responses.

---

## Upgrade Command

```bash
npm install zrb@2
```

*(If you install Zrb via a different package manager, run the equivalent install command for your environment.)*
