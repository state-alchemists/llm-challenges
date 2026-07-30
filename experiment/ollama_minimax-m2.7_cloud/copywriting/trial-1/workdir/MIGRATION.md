# Zrb CLI Migration Guide: v1 to v2

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Each section shows the v1 behavior, the v2 replacement, and what you need to do.

## Breaking Changes

### 1. All Endpoints Are Now Prefixed with `/v2/`

Every endpoint path has changed. There is no v1 compatibility mode.

**v1:**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**v2:**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

### 2. Authentication Header Changed

The header name and format both changed. Requests using the old header receive HTTP 401.

**v1:**
```http
X-Auth-Token: <your_api_key>
```

**v2:**
```http
Authorization: Bearer <your_api_token>
```

Update your HTTP client to send `Authorization: Bearer <token>` on every request.

### 3. Task `id` Is Now a UUID String

Task IDs are no longer integers. They are UUID strings. Code that parses IDs as integers will break.

**v1 task:**
```json
{ "id": 42, ... }
```

**v2 task:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", ... }
```

Update any code that stores, compares, or serializes task IDs to handle UUID strings.

### 4. Field `done` Renamed to `completed`

The `done` boolean field is now called `completed`.

**v1 — update task:**
```json
{ "done": true }
```

**v2 — update task:**
```json
{ "completed": true }
```

Rename all occurrences of `done` to `completed` in your request bodies and response handling.

### 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` field. Omitting it returns HTTP 422.

**v1 — create task:**
```json
{ "title": "New task" }
```

**v2 — create task:**
```json
{ "title": "New task", "project_id": "proj_abc123" }
```

Every `POST /v2/tasks` call must include a valid `project_id`. Fetch or create a project first if you do not have one.

### 6. List Endpoints Return a Paginated Envelope

List responses are no longer bare arrays. They are wrapped in an envelope object with `items`, `total`, and `next_cursor`.

**v1 — list tasks response:**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**v2 — list tasks response:**
```json
{
  "items": [
    { "id": "...", "title": "Buy milk", "completed": false, "project_id": "...", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Update your list-response handling to read `response.items` instead of the root array. Use `response.next_cursor` with `?cursor=` to paginate.

---

## Migration Checklist

- [ ] Update all endpoint paths from `/tasks` to `/v2/tasks`
- [ ] Replace header `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] Change task ID handling from integer to UUID string
- [ ] Rename field `done` to `completed` in all request bodies and response parsing
- [ ] Add `project_id` to every task creation request
- [ ] Update list response parsing to use `response.items` array and handle `response.next_cursor`
- [ ] Test pagination by checking for `next_cursor` and passing it as `?cursor=` query param
- [ ] Verify no remaining references to `X-Auth-Token` or bare array list responses

---

## Upgrade Command

```bash
npm install -g zrb-cli@2
```
