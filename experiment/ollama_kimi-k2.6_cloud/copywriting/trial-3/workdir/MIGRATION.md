# Zrb CLI v1 → v2 Migration Guide

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2.

---

## Breaking Changes

### 1. API endpoints are now version-prefixed

All endpoints moved from `/` to `/v2/`.

**Before (v1)**
```bash
curl -X GET https://api.zrb.dev/tasks
```

**After (v2)**
```bash
curl -X GET https://api.zrb.dev/v2/tasks
```

---

### 2. Authentication header changed

v1 used a custom `X-Auth-Token` header. v2 requires a standard Bearer token.

**Before (v1)**
```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.dev/tasks
```

**After (v2)**
```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.dev/v2/tasks
```

Requests sent with the old `X-Auth-Token` header will receive **HTTP 401**.

---

### 3. Task `id` changed from integer to UUID string

The `id` field on Task objects is now a UUID instead of an auto-incrementing integer. Update any code that assumes numeric IDs or casts them to integers.

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

The boolean status field on Tasks is now named `completed`.

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

This applies to both reading Task objects and writing them in `PUT` requests.

---

### 5. Task creation now requires `project_id`

Creating a Task is now scoped to a project. The `project_id` field is mandatory in `POST /v2/tasks` requests.

**Before (v1)**
```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

**After (v2)**
```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

Omitting `project_id` returns **HTTP 422**.

---

### 6. List endpoints return a paginated envelope

`GET /tasks` no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`.

**Before (v1)**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2)**
```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-f6g7-8901-bcde-f12345678901", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the cursor as a query parameter:

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.dev/v2/tasks?cursor=cursor_xyz&limit=20"
```

---

## Migration Checklist

Use this checklist to upgrade your integration safely.

- [ ] **Update endpoint URLs** — prepend `/v2/` to all API paths.
- [ ] **Rotate authentication** — replace `X-Auth-Token` headers with `Authorization: Bearer <token>`.
- [ ] **Audit ID handling** — update schemas, types, and database columns that expect integer `id` to accept UUID strings.
- [ ] **Rename `done` to `completed`** — update deserialization, JSON payloads, and UI bindings for the Task status field.
- [ ] **Add `project_id` to creation flows** — update every `POST` that creates a Task to include a valid `project_id`.
- [ ] **Adopt pagination** — update list consumers to read `items` from the envelope and loop using `next_cursor`.
- [ ] **Run integration tests** — verify all Task CRUD operations against the v2 endpoints before deploying to production.

---

## Upgrade Command

Upgrade the CLI to v2 with:

```bash
pip install --upgrade zrb
```

After upgrading, run `zrb --version` to confirm you are on v2.x.x.
