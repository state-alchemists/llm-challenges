# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change when upgrading from Zrb v1 to v2. Read it in full before starting your migration.

**Audience:** developers already using v1  
**Time estimate:** 30–60 minutes depending on integration size

---

## Overview of Breaking Changes

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoint prefix `/tasks` → `/v2/tasks` | Update all API base URLs |
| 2 | Auth header `X-Auth-Token` → `Bearer` | Update request headers |
| 3 | Task `id` is now a UUID string | Update ID handling and types |
| 4 | Field `done` renamed to `completed` | Update field references |
| 5 | `project_id` required on task creation | Add project scoping |
| 6 | List returns paginated envelope | Update response parsing |

---

## 1. Endpoint Prefix

All endpoints now carry a `/v2/` prefix.

**Before (v1):**
```http
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

The auth header format has changed. `X-Auth-Token` is no longer accepted.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

Requests lacking a valid `Authorization: Bearer` header return HTTP 401.

---

## 3. Task ID Type

Task IDs changed from auto-incrementing integers to UUID strings.

**Before (v1) — integer ID:**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2) — UUID string ID:**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

Update any code that:
- Stores or caches task IDs as integers
- Constructs URLs with integer IDs
- Validates or parses IDs as non-string types

---

## 4. Field Renamed: `done` → `completed`

The `done` boolean is now named `completed`.

**Before (v1):**
```json
{ "id": 1, "title": "Ship v1", "done": true }
```

**After (v2):**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Ship v2", "completed": true }
```

Update all references to the `done` field in:
- JSON parsing / serialization
- Conditional logic (`task.done`, `task["done"]`)
- Database columns or ORM fields

---

## 5. `project_id` Required on Task Creation

Creating a task now requires a `project_id`. Omitting it returns HTTP 422.

**Before (v1):**
```http
POST /tasks
Content-Type: application/json

{ "title": "New task" }
```

**After (v2):**
```http
POST /v2/tasks
Content-Type: application/json

{ "title": "New task", "project_id": "proj_abc123" }
```

You must:
1. Provision a project (via the Projects API, not covered here) before creating tasks
2. Include `project_id` in every task creation request

---

## 6. Paginated List Response

List endpoints no longer return a bare array. They return an envelope with `items`, `total`, and `next_cursor`.

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
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false },
    { "id": "e5f6g7h8-...", "title": "Ship v2", "completed": true }
  ],
  "total": 2,
  "next_cursor": null
}
```

To fetch subsequent pages, pass the `next_cursor` value as a query parameter:

```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

Update your list-parsing logic to read `response.items` instead of the root array.

---

## Migration Checklist

Run through these steps in order:

- [ ] **Update base URL** — add `/v2` to every endpoint path
- [ ] **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer`
- [ ] **Update ID handling** — change ID fields/types from `int` to `string` (UUID)
- [ ] **Rename `done` → `completed`** — find and replace in all request/response code
- [ ] **Add `project_id` to task creation** — fetch or provision a project first
- [ ] **Update list parsing** — read `response.items` and use `response.next_cursor` for pagination
- [ ] **Update tests** — align fixtures and assertions with v2 response shapes
- [ ] **Verify** — run your integration suite against the v2 endpoint

---

## Upgrade Command

Once your code is updated:

```bash
pip install zrb-cli --upgrade
```

Confirm the version:

```bash
zrb --version
```

Expect output reporting v2.x.
