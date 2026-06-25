# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, pagination, and stricter authentication. This guide covers every breaking change you need to address when upgrading from v1.

If you are already running v1 in production, plan for the following six changes before deploying v2.

---

## 1. API Version Prefix

All endpoints are now namespaced under `/v2/`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**
```bash
curl -X GET https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl -X GET https://api.zrb.io/v2/tasks
```

---

## 2. Authentication Header

The `X-Auth-Token` header is removed. v2 uses a standard Bearer token.

| v1 | v2 |
|---|---|
| `X-Auth-Token: <your_api_key>` | `Authorization: Bearer <your_api_token>` |

Requests sent with the old header will receive `HTTP 401 Unauthorized`.

**Before (v1):**
```bash
curl -H "X-Auth-Token: abc123" \
  https://api.zrb.io/tasks
```

**After (v2):**
```bash
curl -H "Authorization: Bearer abc123" \
  https://api.zrb.io/v2/tasks
```

---

## 3. Task ID Type Changed to UUID

Task `id` is no longer an integer. All IDs are now UUID strings.

| v1 | v2 |
|---|---|
| `42` | `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

Update any client-side code that assumes integer IDs, performs numeric comparisons, or relies on auto-increment ordering.

**Before (v1):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2):**
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

## 4. Field Rename: `done` → `completed`

The boolean field indicating task completion has been renamed.

| v1 | v2 |
|---|---|
| `done` | `completed` |

Update request bodies, response parsing, and any stored JSON that references the old field name.

**Before (v1):**
```bash
curl -X PUT https://api.zrb.io/tasks/42 \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

**After (v2):**
```bash
curl -X PUT https://api.zrb.io/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer abc123" \
  -d '{"completed": true}'
```

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Omitting it returns `HTTP 422 Unprocessable Entity`.

**Before (v1):**
```bash
curl -X POST https://api.zrb.io/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**
```bash
curl -X POST https://api.zrb.io/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer abc123" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

---

## 6. Paginated List Responses

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
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

Fetch the next page by passing the cursor:

```bash
curl "https://api.zrb.io/v2/tasks?cursor=cursor_xyz&limit=20" \
  -H "Authorization: Bearer abc123"
```

---

## Migration Checklist

Use this checklist to verify every integration point before going live on v2.

- [ ] **Update base URL** — prepend `/v2/` to all endpoint paths.
- [ ] **Replace auth header** — switch `X-Auth-Token` to `Authorization: Bearer <token>`.
- [ ] **Migrate ID handling** — replace integer IDs with UUID strings in URLs, request bodies, and databases.
- [ ] **Rename `done` to `completed`** — update request payloads, response parsing, and stored JSON.
- [ ] **Add `project_id` to task creation** — ensure every `POST /v2/tasks` payload includes a valid `project_id`.
- [ ] **Adopt paginated list parsing** — update list-task consumers to read `response.items` instead of treating the response as an array.
- [ ] **Add pagination support** — implement `cursor` query-param traversal for list endpoints.
- [ ] **Run integration tests** — verify all CRUD operations against a v2 staging environment.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
pip install --upgrade zrb
```

Confirm the installed version:

```bash
zrb --version
```

You should see `2.x.x`. Once confirmed, run through the checklist above before deploying to production.
