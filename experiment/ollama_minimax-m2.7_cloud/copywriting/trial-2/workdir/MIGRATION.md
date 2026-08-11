# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Read through each section, update your code accordingly, then run the upgrade command at the bottom.

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | URL prefix | `/tasks` | `/v2/tasks` |
| 2 | Auth header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Task status field | `done` | `completed` |
| 5 | Create task | no project required | `project_id` required |
| 6 | List response | bare array | paginated envelope |

---

## 1. URL Prefix Changed

All endpoints now live under `/v2/`.

**Before (v1):**
```
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header Changed

The custom `X-Auth-Token` header is replaced with a standard Bearer token.

**Before (v1):**
```http
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
Authorization: Bearer your_api_token_here
```

> ⚠️ Requests using `X-Auth-Token` will receive **HTTP 401**. Update your request headers before upgrading.

---

## 3. Task `id` Type Changed

Task IDs are now UUID strings instead of integers.

**Before (v1) — integer ID:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2) — UUID string ID:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

If your code parses or stores task IDs, update it to handle strings and expect the UUID format.

---

## 4. Status Field Renamed

The `done` field is renamed to `completed`.

**Before (v1):**
```json
{ "id": 1, "title": "Ship v1", "done": true }
```

**After (v2):**
```json
{ "id": "a1b2c3d4-...", "title": "Ship v1", "completed": true }
```

Update all references to `done` in your code — reading task objects, setting task state, conditional checks, etc.

---

## 5. Create Task Requires `project_id`

Task creation now requires a `project_id`. Omitting it returns **HTTP 422**.

**Before (v1):**
```json
POST /tasks
{
  "title": "New task title"
}
```

**After (v2):**
```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Add `project_id` to every task creation call. You'll need to know the target project ID — refer to the Projects API documentation (separate doc).

---

## 6. List Response Format Changed

List endpoints no longer return a bare array. They return a paginated envelope.

**Before (v1) — bare array:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) — paginated envelope:**
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

To fetch the next page, pass `?cursor=<next_cursor>`:
```
GET /v2/tasks?cursor=cursor_xyz
```

Update any code that iterates directly over the list response — it now needs to read `response.items` instead.

---

## Migration Checklist

- [ ] Update all endpoint URLs from `/tasks` to `/v2/tasks`
- [ ] Replace `X-Auth-Token` header with `Authorization: Bearer <token>`
- [ ] Change task ID parsing from integer to UUID string
- [ ] Rename all `done` field references to `completed`
- [ ] Add `project_id` to every task creation request
- [ ] Update list response handling to read `response.items` (not the root array)
- [ ] Add pagination logic using `next_cursor` for large result sets
- [ ] Update any stored task IDs or references to use UUID format
- [ ] Update client-side type definitions (if using TypeScript or similar)
- [ ] Run your test suite and update any affected assertions

---

## Upgrade Command

```bash
npm install -g zrb-cli@latest
```

Or, if you use a package manager:

```bash
# Yarn
yarn global add zrb-cli@latest

# Homebrew (macOS)
brew upgrade zrb-cli
```

> After upgrading, test your integration against the v2 endpoints before deploying to production. Use a staging environment if you have one.
