# Zrb CLI Migration Guide: v1 → v2

This guide walks you through every breaking change in Zrb v2 and how to update your code.

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoint prefix `/v2/` added | All routes changed |
| 2 | Auth header `X-Auth-Token` → `Authorization: Bearer` | Auth method replaced |
| 3 | Task `id` is now a UUID string, not integer | Type change, affects all references |
| 4 | Field `done` renamed to `completed` | JSON key change |
| 5 | Task creation requires `project_id` | New required field |
| 6 | List endpoints return paginated envelope | Response structure change |

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

The `X-Auth-Token` header is no longer accepted. Use Bearer token auth instead.

**Before (v1)**
```http
X-Auth-Token: your_api_key_here
```

**After (v2)**
```http
Authorization: Bearer your_api_token_here
```

Requests without a valid Bearer token will receive `401 Unauthorized`.

---

## 3. Task ID Type

Task IDs changed from auto-incremented integers to UUID strings.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

Update any code that parses or stores task IDs — what was an `int` is now a `string`, and URL paths change accordingly (e.g., `/tasks/42` → `/v2/tasks/a1b2c3d4-...`).

---

## 4. Field Renamed: `done` → `completed`

The boolean completion flag is now named `completed` instead of `done`.

**Before (v1)**
```json
{ "id": 1, "title": "Ship v1", "done": true }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-...", "title": "Ship v1", "completed": true }
```

Search your codebase for `.done`, `["done"]`, and `"done"` occurrences and rename them.

---

## 5. `project_id` Required on Task Creation

Creating a task now requires a `project_id`. Omitting it returns HTTP 422.

**Before (v1)**
```http
POST /tasks
{ "title": "New task title" }
```

**After (v2)**
```http
POST /v2/tasks
{ "title": "New task title", "project_id": "proj_abc123" }
```

You must provision a project before creating tasks. Contact your Zrb admin to create one, or use the Projects API (out of scope for this guide).

---

## 6. List Response Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`.

**Before (v1)**
```json
[
  { "id": 1, "title": "Buy milk", "done": false },
  { "id": 2, "title": "Ship v1", "done": true }
]
```

**After (v2)**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123" },
    { "id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123" }
  ],
  "total": 2,
  "next_cursor": null
}
```

To fetch the next page, pass `?cursor=<next_cursor>` on the subsequent request.

---

## Migration Checklist

Run through these steps in order:

- [ ] **Update base URL** — prepend `/v2` to every endpoint path
- [ ] **Replace auth header** — change `X-Auth-Token` to `Authorization: Bearer`
- [ ] **Update ID handling** — change task ID parsing from `int` to `string` (UUID)
- [ ] **Rename `done` → `completed`** — update all JSON key references
- [ ] **Add `project_id` to task creation** — include it in every `POST /v2/tasks` body
- [ ] **Update list response parsing** — adapt from array to `{items, total, next_cursor}`
- [ ] **Add pagination logic** — handle `next_cursor` for large result sets
- [ ] **Update tests and mocks** — ensure test fixtures reflect v2 shapes
- [ ] **Point production traffic to v2** — once all above are confirmed

---

## Upgrade Command

```bash
npm install zrb@latest
# or
pip install zrb --upgrade
```

Replace `npm` with your package manager of choice. Verify the upgrade:

```bash
zrb --version
```

After upgrading, test your integration against the v2 endpoints before moving production traffic.