# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change between Zrb CLI v1 and v2, with before/after examples and a step-by-step checklist to migrate your integration.

---

## Breaking Changes Overview

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Completion field | `done` | `completed` |
| 5 | Create requires | `title` only | `title` + `project_id` |
| 6 | List response | bare array | paginated envelope |

---

## 1. Endpoint Prefix

All endpoints now live under `/v2/`.

**Before (v1)**
```http
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2)**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

The header name and format have changed. Requests using `X-Auth-Token` will receive **HTTP 401**.

**Before (v1)**
```http
X-Auth-Token: your_api_key_here
```

**After (v2)**
```http
Authorization: Bearer your_api_token_here
```

---

## 3. Task ID Type

Task IDs changed from auto-incrementing integers to UUID strings. Update any code that parses or stores task IDs.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

If you store IDs in a typed field (e.g., `int` in a database column), migrate to `string` / `text`.

---

## 4. Completion Field Renamed

The `done` boolean is now named `completed`. Update all field references in requests and responses.

**Before (v1) — Update request**
```json
{ "title": "Updated title", "done": true }
```

**After (v2) — Update request**
```json
{ "title": "Updated title", "completed": true }
```

---

## 5. Create Task Requires Project ID

Task creation now requires a `project_id`. Omitting it returns **HTTP 422**.

**Before (v1) — Create request**
```json
{ "title": "New task title" }
```

**After (v2) — Create request**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

You must provision at least one project in the v2 dashboard and supply its ID when creating tasks.

---

## 6. List Response: Paginated Envelope

List endpoints no longer return a bare array. They return a wrapper object with `items`, `total`, and `next_cursor`.

**Before (v1) — List response**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2) — List response**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "e5f6a789-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 2,
  "next_cursor": null
}
```

To fetch the next page, pass `?cursor=<next_cursor>` on the request.

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Change task ID type in your code from `int` to `string`
- [ ] Rename `done` field to `completed` in all request/response handling
- [ ] Add `project_id` to every task creation call
- [ ] Update list response parsing: access `response.items` instead of `response` directly
- [ ] Add pagination loop if you consume all pages (check `next_cursor`)
- [ ] Update any stored task IDs or database columns to UUID strings
- [ ] Test against the v2 endpoint before deploying to production

---

## Upgrade Command

```bash
npm install @zrb/cli@2
```

Or, if you prefer yarn:

```bash
yarn add @zrb/cli@2
```
