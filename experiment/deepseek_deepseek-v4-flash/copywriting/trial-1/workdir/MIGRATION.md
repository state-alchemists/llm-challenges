# Migrating from Zrb Task API v1 to v2

This guide walks you through every breaking change between v1 and v2 of the Zrb Task API. Read it before upgrading so nothing catches you by surprise.

v2 introduces **projects**, **pagination**, and **stricter authentication**. Existing v1 clients will receive `401`, `404`, or malformed-data errors if they call v2 endpoints without updating. Plan for a coordinated cutover.

---

## Table of Contents

- [Breaking Change 1: Endpoint Prefix — `/v2/`](#breaking-change-1-endpoint-prefix--v2)
- [Breaking Change 2: Authentication Header — Bearer Token](#breaking-change-2-authentication-header--bearer-token)
- [Breaking Change 3: Task `id` — Integer to UUID](#breaking-change-3-task-id--integer-to-uuid)
- [Breaking Change 4: Field Rename — `done` → `completed`](#breaking-change-4-field-rename--done--completed)
- [Breaking Change 5: New Required Field — `project_id`](#breaking-change-5-new-required-field--project_id)
- [Breaking Change 6: List Response — Paginated Envelope](#breaking-change-6-list-response--paginated-envelope)
- [Migration Checklist](#migration-checklist)
- [Upgrade](#upgrade)

---

## Breaking Change 1: Endpoint Prefix — `/v2/`

All endpoints are now prefixed with `/v2/`. v1 paths (`/tasks`, `/tasks/{id}`) return `404`.

**Before (v1)**

```
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2)**

```
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Action:** Update your base URL or route map to prepend `/v2/` to every endpoint path.

---

## Breaking Change 2: Authentication Header — Bearer Token

The old `X-Auth-Token` header is deprecated. v2 requires an `Authorization` header with a Bearer token. Requests using `X-Auth-Token` receive `401`.

**Before (v1)**

```
X-Auth-Token: sk-abc123
```

**After (v2)**

```
Authorization: Bearer sk-abc123
```

**Action:** Replace the `X-Auth-Token` header with `Authorization: Bearer <token>` in every request.

---

## Breaking Change 3: Task `id` — Integer to UUID

Task identifiers are now UUID strings instead of auto-incrementing integers. All endpoints that accept `{id}` (`GET`, `PUT`, `DELETE`) now expect a UUID string. Responses will contain UUIDs.

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

**Action:**
- Update any stored task IDs from integers to UUIDs. v2 does not map old integer IDs — seed your new system with fresh UUIDs from the live v2 API.
- Change the type of `id` fields in client models/types from `int`/`number` to `string`.
- Update URL construction: `GET /v2/tasks/42` → `GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890`.

---

## Breaking Change 4: Field Rename — `done` → `completed`

The boolean field `done` is renamed to `completed` in both request and response payloads. Writing `done` to a v2 endpoint silently produces an extra field that v2 ignores — your update won't take effect.

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

**Action:** Replace all occurrences of `done` with `completed` in Create and Update request payloads, and in any code that reads the field from response objects.

---

## Breaking Change 5: New Required Field — `project_id`

Task creation now requires a `project_id` string. Omitting it returns `422`. Update the `project_id` field on existing tasks is optional (PUT only sends fields you want to change), but creation always requires it.

**Before (v1)**

```json
POST /tasks
{
  "title": "New task title"
}
```

**After (v2)**

```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Action:** Ensure every `POST /v2/tasks` call includes `project_id`. Obtain valid project IDs from your project management workflow (v2 introduces the concept — you will need to create or reference a project before creating tasks under it).

---

## Breaking Change 6: List Response — Paginated Envelope

`GET /tasks` used to return a bare array. `GET /v2/tasks` now returns a paginated envelope with `items`, `total`, and `next_cursor`. The familiar array access pattern (`response[0].title`) no longer works. Use `cursor` and `limit` query parameters to navigate pages.

**Before (v1)**

```json
GET /tasks
→ [
    {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
    {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
  ]
```

Client code (JavaScript example):

```javascript
const tasks = await fetch('/tasks').then(r => r.json());
tasks.forEach(t => console.log(t.title));
```

**After (v2)**

```json
GET /v2/tasks?limit=20
→ {
    "items": [
      {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_...", "created_at": "..."},
      {"id": "c3d4...", "title": "Ship v2", "completed": true, "project_id": "proj_...", "created_at": "..."}
    ],
    "total": 42,
    "next_cursor": "cursor_xyz"
  }
```

Client code (JavaScript example):

```javascript
const { items, total, next_cursor } = await fetch('/v2/tasks?limit=20').then(r => r.json());
items.forEach(t => console.log(t.title));
```

To fetch all pages:

```javascript
let cursor;
do {
  const params = new URLSearchParams({ limit: 20 });
  if (cursor) params.set('cursor', cursor);
  const res = await fetch(`/v2/tasks?${params}`).then(r => r.json());
  res.items.forEach(t => console.log(t.title));
  cursor = res.next_cursor;
} while (cursor);
```

**Action:**
- Update response parsing to read from `response.items` instead of `response[index]`.
- If you rely on `response.length` for counting, use `response.total` instead.
- Implement cursor-based pagination if you need to traverse the full result set.

---

## Migration Checklist

Use this checklist to track your migration progress. Complete items in the order listed.

- [ ] **1. Update base URL / route prefix** — Prepend `/v2/` to all endpoint paths (`/tasks` → `/v2/tasks`).
- [ ] **2. Replace auth header** — Change `X-Auth-Token` to `Authorization: Bearer <token>` in every request.
- [ ] **3. Migrate task IDs** — Re-seed task identifiers as UUID strings. Update all client models, storage, and URL builders that use integer IDs.
- [ ] **4. Rename `done` → `completed`** — Update all request payloads and response readers. Check for `done` in serializers, deserializers, database models, UI state, and tests.
- [ ] **5. Add `project_id` to Create Task** — Ensure every task creation flow includes a valid `project_id`. Establish the workflow for obtaining or creating projects first.
- [ ] **6. Rewrite list response parsing** — Switch from bare-array access (`response[i]`) to envelope access (`response.items[i]`). Update page-length logic and add cursor iteration if needed.
- [ ] **7. Update API client tests** — Run your test suite against the v2 endpoints and fix any failures.
- [ ] **8. Deploy and monitor** — Roll out the updated client alongside the v2 server. Watch for `401`, `404`, and `422` errors as signals of incomplete migration.

---

## Upgrade

To start using v2, update your dependency:

```bash
zrb upgrade --version 2.0.0
```

Once upgraded, verify the new endpoints respond as expected:

```bash
zrb task list 2>/dev/null | head -5
```
