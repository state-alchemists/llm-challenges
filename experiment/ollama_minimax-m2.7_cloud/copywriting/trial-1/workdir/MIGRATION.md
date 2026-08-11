# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change between Zrb Task API v1 and v2, with before/after examples and a step-by-step checklist to migrate your integration.

---

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Auth header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task ID type | integer | UUID string |
| 4 | Status field | `done` | `completed` |
| 5 | Create requires | `title` only | `title` + `project_id` |
| 6 | List response | bare array | paginated envelope |

---

## 1. Endpoint Prefix

All endpoints now include the `/v2/` version prefix.

**Before (v1)**
```
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2)**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

The auth header has changed from a custom header to a standard Bearer token scheme.

**Before (v1)**
```http
X-Auth-Token: your_api_key_here
```

**After (v2)**
```http
Authorization: Bearer your_api_token_here
```

> ⚠️ Requests using `X-Auth-Token` will receive **HTTP 401**. Update your headers before upgrading.

---

## 3. Task ID Type

Task IDs are now UUID strings instead of integers. Update any code that parses or stores task IDs.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", ... }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", ... }
```

> ⚠️ Update your ID storage (database columns, cache keys, etc.) from `INTEGER` to `STRING`/`VARCHAR`.

---

## 4. Status Field Renamed

The `done` boolean is renamed to `completed`.

**Before (v1) — Update Task**
```json
{ "done": true }
```

**After (v2) — Update Task**
```json
{ "completed": true }
```

> ⚠️ Rename this field in your request bodies and any stored task representations.

---

## 5. Task Creation Requires Project ID

Creating a task now requires a `project_id`. This is a **required** field — omitting it returns **HTTP 422**.

**Before (v1) — Create Task**
```json
{ "title": "New task title" }
```

**After (v2) — Create Task**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

> ⚠️ Obtain a `project_id` before creating tasks. Projects are managed separately in v2.

---

## 6. List Response Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1) — List Tasks**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2) — List Tasks**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 2,
  "next_cursor": null
}
```

To fetch subsequent pages, pass the `next_cursor` value as a query parameter:

```
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

> ⚠️ Update your list parsing logic to read `response.items` instead of the root array, and use `response.next_cursor` for pagination.

---

## Step-by-Step Migration Checklist

- [ ] **Update endpoint URLs** — prepend `/v2/` to all task paths
- [ ] **Update auth header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update ID handling** — change task ID type from integer to UUID string in your code and storage
- [ ] **Rename `done` → `completed`** — update all request bodies and data models
- [ ] **Add `project_id` to task creation** — fetch or create a project first, then include `project_id` when creating tasks
- [ ] **Update list parsing** — change code that reads list responses to use `response.items`, `response.total`, and `response.next_cursor`
- [ ] **Implement cursor pagination** — if you paginate through lists, use `?cursor=<next_cursor>` to fetch subsequent pages
- [ ] **Update stored task objects** — rename the `done` field and change `id` type in any persisted task data
- [ ] **Test with a sandbox project** — verify all CRUD operations work end-to-end before migrating production

---

## Upgrade Command

Once you have completed the checklist:

```bash
npm install @zrb/cli@latest
```

Or, if you prefer Yarn:

```bash
yarn global add @zrb/cli@latest
```

> Always test against the v2 sandbox environment before updating production integrations.
