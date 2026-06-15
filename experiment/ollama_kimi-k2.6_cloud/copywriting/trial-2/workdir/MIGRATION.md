# Migrating from Zrb API v1 to v2

Zrb API v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change you need to address when upgrading from v1.

**TL;DR** — the six breaking changes are:
1. All endpoints now live under `/v2/`
2. `X-Auth-Token` header replaced by `Authorization: Bearer`
3. Task `id` changed from integer to UUID string
4. Task field `done` renamed to `completed`
5. Creating a task now requires a `project_id`
6. List endpoints return a paginated envelope instead of a bare array

---

## 1. API Version Prefix

All endpoints are now prefixed with `/v2/`. Requests to the old paths will not be routed.

### Before (v1)

```bash
curl https://api.zrb.io/tasks \
  -H "X-Auth-Token: $TOKEN"
```

### After (v2)

```bash
curl https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer $TOKEN"
```

---

## 2. Authentication Header

The custom `X-Auth-Token` header is removed. v2 uses a standard Bearer token in the `Authorization` header. Requests sent with `X-Auth-Token` will receive HTTP 401.

### Before (v1)

```bash
curl https://api.zrb.io/tasks/42 \
  -H "X-Auth-Token: $API_KEY"
```

### After (v2)

```bash
curl https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer $API_TOKEN"
```

---

## 3. Task `id` Type Changed to UUID

Task identifiers are no longer integers. Every task now has a UUID string `id`. Update any code that assumes numeric IDs or performs integer operations on them.

### Before (v1)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2)

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

## 4. Task Field `done` Renamed to `completed`

The boolean flag indicating whether a task is finished has been renamed from `done` to `completed`. Sending `done` in a request body will be ignored and may trigger validation errors.

### Before (v1)

```bash
curl -X PUT https://api.zrb.io/tasks/42 \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated title", "done": true}'
```

### After (v2)

```bash
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated title", "completed": true}'
```

---

## 5. Task Creation Requires `project_id`

Every task must belong to a project. The `POST /v2/tasks` endpoint now requires a `project_id` field in the request body. Omitting it returns HTTP 422 Unprocessable Entity.

### Before (v1)

```bash
curl -X POST https://api.zrb.io/tasks \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

### After (v2)

```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

## 6. List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`. You must update deserialization logic and implement cursor-based pagination if you previously consumed the entire list in one call.

### Before (v1)

```bash
curl https://api.zrb.io/tasks \
  -H "X-Auth-Token: $TOKEN"
```

**Response:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)

```bash
curl "https://api.zrb.io/v2/tasks?limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

**Response:**

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the cursor:

```bash
curl "https://api.zrb.io/v2/tasks?limit=20&cursor=cursor_xyz" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Migration Checklist

Use this checklist to verify your upgrade is complete.

- [ ] Update all request URLs from `/tasks` to `/v2/tasks` (and other endpoints as applicable)
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Change task `id` storage and serialization from integer to UUID string
- [ ] Rename all references to the `done` field to `completed`
- [ ] Add a required `project_id` to every task creation call
- [ ] Update list-task deserialization from bare array to paginated envelope (`items`, `total`, `next_cursor`)
- [ ] Implement cursor-based pagination if your application iterates over all tasks
- [ ] Update integration tests to expect v2 response shapes and status codes
- [ ] Rotate or re-issue API tokens if your token format has changed

---

## Upgrade Command

Install the latest v2 CLI to begin using the new API:

```bash
pip install --upgrade zrb>=2.0.0
```
