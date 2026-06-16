# Zrb CLI v2 Migration Guide

This guide covers every breaking change from v1 to v2 and how to update your integration.

**Estimated migration time:** 30–60 minutes depending on codebase size.

---

## Breaking Changes

### 1. Endpoint Prefix Changed

All endpoints now live under `/v2/`.

| Operation | v1 | v2 |
|-----------|----|----|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key
```

**After (v2):**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token
```

---

### 2. Authentication Header

The auth header changed from `X-Auth-Token` to a Bearer token in `Authorization`.

**Before (v1):**
```http
X-Auth-Token: your_api_key
```

**After (v2):**
```http
Authorization: Bearer your_api_token
```

Requests using `X-Auth-Token` will receive **HTTP 401** and must be updated.

---

### 3. Task ID Type: Integer → UUID

Task IDs are now UUID strings instead of integers.

**Before (v1):**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2):**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

Update any code that parses or stores task IDs to expect a string. This affects route parameters, database columns, and client-side state.

---

### 4. Field Renamed: `done` → `completed`

The task completion flag was renamed.

| v1 | v2 |
|----|----|
| `"done": true` | `"completed": true` |

**Before (v1) — updating a task:**
```json
{ "done": true }
```

**After (v2):**
```json
{ "completed": true }
```

Replace all occurrences of `"done"` in your request bodies and response handling.

---

### 5. Create Task Requires `project_id`

Task creation now requires a `project_id` field. Omitting it returns **HTTP 422**.

**Before (v1):**
```json
{ "title": "New task title" }
```

**After (v2):**
```json
{ "title": "New task title", "project_id": "proj_abc123" }
```

You must provision a project before creating tasks. See your project dashboard or use `POST /v2/projects` to create one.

---

### 6. List Response: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1):**
```json
[
  { "id": 1, "title": "Buy milk", "done": false },
  { "id": 2, "title": "Ship v1", "done": true }
]
```

**After (v2):**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123" },
    { "id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123" }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>` on the subsequent request.

---

## Migration Checklist

Work through these steps in order:

- [ ] **Update endpoint base URL** — prepend `/v2` to every task route
- [ ] **Update authentication header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update task ID handling** — change ID fields from `int` to `str`; update route parameters, DB columns, and type annotations
- [ ] **Replace `done` field** — rename all occurrences to `completed` in request bodies and response parsing
- [ ] **Add `project_id` to task creation** — include `project_id` in every `POST /v2/tasks` body; provision projects if you have none
- [ ] **Update list response parsing** — unwrap the `items` array from the envelope; use `total` for count; implement cursor-based pagination if you page through results
- [ ] **Run your test suite** — verify all integrations pass with v2 endpoints
- [ ] **Monitor logs** — check for any `401` or `422` responses indicating missed updates

---

## Upgrade Command

Once your codebase is updated:

```bash
pip install --upgrade zrb-cli
```

Verify the installed version:

```bash
zrb --version
```

Confirm the output shows `2.x.x` before using the CLI against production.