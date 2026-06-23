# Zrb CLI v1 to v2 Migration Guide

v2 introduces projects, pagination, and stricter authentication. Six breaking changes affect every integration. This guide walks through each one with before/after examples and a step-by-step checklist to get you live on v2.

---

## Breaking Changes Overview

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token` | `Authorization: Bearer <token>` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Status field | `done` | `completed` |
| 5 | Create required field | (none) | `project_id` |
| 6 | List response shape | bare array | paginated envelope |

---

## 1. Endpoint Prefix

All endpoints now carry a `/v2/` prefix. Requests to v1 paths return `404`.

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

The header name and format both changed. Tokens remain the same; only the header key and value wrapping changed.

**Before (v1)**

```http
X-Auth-Token: your_api_key_here
```

**After (v2)**

```http
Authorization: Bearer your_api_key_here
```

Requests that still send `X-Auth-Token` will receive `401 Unauthorized`.

---

## 3. Task ID Type

Task IDs changed from auto-incrementing integers to UUID strings. Any code that parses or stores IDs as integers will break.

**Before (v1) — response**

```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z" }
```

**After (v2) — response**

```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z" }
```

Update any ID storage columns to `TEXT` or `VARCHAR(36)`, and update parsing logic to expect a string.

---

## 4. Status Field Renamed

`done` is now `completed`. This affects task objects in all responses and in any update request bodies.

**Before (v1) — update request**

```json
{ "done": true }
```

**After (v2) — update request**

```json
{ "completed": true }
```

---

## 5. Create Requires Project ID

Task creation now requires a `project_id`. Omitting it returns `422 Unprocessable Entity`.

**Before (v1) — create request**

```json
{ "title": "New task title" }
```

**After (v2) — create request**

```json
{ "title": "New task title", "project_id": "proj_abc123" }
```

If you do not yet use projects, create one first:

```http
POST /v2/projects
{ "name": "My Project" }
```

Use the returned `project_id` when creating tasks.

---

## 6. List Response Shape

All list endpoints return a paginated envelope instead of a bare array. The array is now under the `items` key.

**Before (v1) — list response**

```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2) — list response**

```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 2,
  "next_cursor": null
}
```

Iterate over `response.items` instead of the response root. Use `response.next_cursor` with `?cursor=` to paginate.

---

## Step-by-Step Migration Checklist

- [ ] **Update endpoint base URL** — change every `/tasks` to `/v2/tasks` in your client code or configuration.
- [ ] **Update authentication header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Migrate task ID storage** — if you store IDs in a database, change the column type from integer to `TEXT`/`VARCHAR(36)`.
- [ ] **Update ID parsing** — ensure your code treats task IDs as strings, not integers.
- [ ] **Replace `done` with `completed`** — rename the field in your data models, serializers, and update request payloads.
- [ ] **Provision a project** — if you have no existing project, call `POST /v2/projects` to get a `project_id`.
- [ ] **Add `project_id` to create calls** — include the required `project_id` field in every task creation request.
- [ ] **Update list response handling** — change iteration from `response` to `response.items`; add cursor-based pagination using `next_cursor`.
- [ ] **Test in staging** — point your integration at the v2 endpoint and run your full test suite before deploying to production.

---

## Upgrade Command

Once your code is updated and tested:

```bash
pip install --upgrade zrb-cli
```