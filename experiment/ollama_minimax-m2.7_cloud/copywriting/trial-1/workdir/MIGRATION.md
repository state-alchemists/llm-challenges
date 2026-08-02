# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change between Zrb CLI v1 and v2, with before/after examples and a step-by-step checklist to migrate your integration.

## Breaking Changes at a Glance

| # | Change | Summary |
|---|--------|---------|
| 1 | Endpoint prefix | All paths now start with `/v2/` |
| 2 | Authentication header | `X-Auth-Token` → `Authorization: Bearer` |
| 3 | Task `id` type | Integer → UUID string |
| 4 | Task field renamed | `done` → `completed` |
| 5 | Task creation requirement | `project_id` is now required |
| 6 | List response format | Bare array → paginated envelope |

---

## 1. Endpoint Prefix

Every endpoint is now versioned under `/v2/`.

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

The header key has changed from `X-Auth-Token` to a standard Bearer token.

**Before (v1)**
```http
X-Auth-Token: your_api_key_here
```

**After (v2)**
```http
Authorization: Bearer your_api_token_here
```

Requests using `X-Auth-Token` will now receive `401 Unauthorized`.

---

## 3. Task `id` Type

Task IDs are no longer integers. They are now UUID strings.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z" }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z" }
```

Update any code that parses or stores task IDs — integer comparisons and arithmetic will break.

---

## 4. Task Field Renamed: `done` → `completed`

The `done` boolean field is renamed to `completed`.

**Before (v1)**
```json
{ "title": "Ship v2", "done": true }
```

**After (v2)**
```json
{ "title": "Ship v2", "completed": true }
```

This affects request bodies for update calls and response bodies in all endpoints.

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before (v1)**
```http
POST /tasks
Content-Type: application/json

{ "title": "New task" }
```

**After (v2)**
```http
POST /v2/tasks
Content-Type: application/json

{ "title": "New task", "project_id": "proj_abc123" }
```

Ensure you have a valid `project_id` before creating tasks. See your project documentation to create or list available projects.

---

## 6. List Response Format: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a wrapper envelope with `items`, `total`, and `next_cursor`.

**Before (v1)**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2)**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "e5f6g7h8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass `?cursor=<next_cursor>` on the subsequent request. The `limit` query param controls page size (default: 20).

---

## Migration Checklist

Run through these steps in order for each service that integrates with Zrb CLI.

- [ ] **Update endpoint base URL** — prepend `/v2` to every Zrb API path
- [ ] **Update authentication header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update task ID handling** — change ID variables from `int` to `string` (or UUID); update any database columns, caches, or serialization logic
- [ ] **Replace `done` field with `completed`** — update request/response parsing, database columns, and UI labels
- [ ] **Add `project_id` to task creation** — obtain a valid `project_id` and include it in every `POST /v2/tasks` body
- [ ] **Update list response parsing** — change loop/code that iterates over list responses to read `items[]` from the envelope; extract `total` and `next_cursor` for pagination
- [ ] **Implement cursor-based pagination** — if you currently page through lists, replace offset/page logic with cursor logic using `next_cursor`
- [ ] **Run integration tests** — verify all CRUD operations against the v2 endpoints
- [ ] **Deploy and monitor** — watch for `401` (bad auth header), `422` (missing `project_id`), and `404` (old integer IDs still in storage)

---

## Upgrade Command

```bash
npm install @zrb/cli@2
```

Or, if you prefer Yarn:

```bash
yarn add @zrb/cli@2
```
