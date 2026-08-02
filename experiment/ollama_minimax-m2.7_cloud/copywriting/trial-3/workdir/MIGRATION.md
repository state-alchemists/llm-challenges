# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change between Zrb CLI v1 and v2, with before/after examples and a step-by-step checklist to migrate your integration.

---

## What's New in v2

- **Projects** — tasks are now scoped to projects
- **Pagination** — list endpoints use cursor-based pagination
- **Stricter auth** — Bearer token authentication replaces the `X-Auth-Token` header

---

## Breaking Changes

### 1. Base URL prefix changed

All endpoints are now prefixed with `/v2/`.

| v1 | v2 |
|---|---|
| `GET /tasks` | `GET /v2/tasks` |
| `POST /tasks` | `POST /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

---

### 2. Authentication header changed

The custom `X-Auth-Token` header is no longer accepted. Switch to Bearer token authentication.

**Before (v1):**

```http
X-Auth-Token: your_api_key_here
```

**After (v2):**

```http
Authorization: Bearer your_api_token_here
```

Requests that still use `X-Auth-Token` will receive **HTTP 401**.

---

### 3. Task `id` type changed from integer to UUID string

Task IDs are no longer integers. They are now UUID strings.

**Before (v1) — response:**

```json
{ "id": 42, "title": "Write tests", "done": false, "created_at": "..." }
```

**After (v2) — response:**

```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "..." }
```

Update any code that parses or stores task IDs to expect a string. This affects request paths (e.g., `GET /v2/tasks/42` → `GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890`) and any database columns typed as integer.

---

### 4. Task field `done` renamed to `completed`

The `done` field on task objects is replaced by `completed`.

**Before (v1) — update request body:**

```json
{ "done": true }
```

**After (v2) — update request body:**

```json
{ "completed": true }
```

This applies to both the **Update Task** (`PUT /v2/tasks/{id}`) and **Create Task** request bodies (though in v2 create you do not set `completed`; it defaults to `false`).

---

### 5. Task creation now requires `project_id`

Tasks can no longer be created without a project. The `project_id` field is **required** on `POST /v2/tasks`.

**Before (v1) — create task:**

```json
{ "title": "New task title" }
```

**After (v2) — create task:**

```json
{ "title": "New task title", "project_id": "proj_abc123" }
```

Omitting `project_id` returns **HTTP 422**. You must create or obtain a project ID first (via the Projects API, out of scope for this guide) before creating tasks.

---

### 6. List endpoints return a paginated envelope instead of a bare array

List endpoints no longer return a bare array. They return a wrapper envelope with `items`, `total`, and `next_cursor`.

**Before (v1) — `GET /tasks`:**

```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2) — `GET /v2/tasks`:**

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

To fetch the next page, pass `?cursor=<next_cursor>` on the same endpoint. The `limit` query parameter controls page size (default: 20).

---

## Migration Checklist

Run through these steps in order. Mark each as done as you update your integration.

- [ ] **Update base URL** — prepend `/v2` to every endpoint path
- [ ] **Switch auth header** — replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update task ID handling** — change any integer task ID fields to strings; update request paths that embed task IDs
- [ ] **Rename `done` → `completed`** — find and replace `done` in request bodies and response parsing
- [ ] **Add `project_id` to task creation** — every `POST /v2/tasks` call needs a `project_id`; obtain project IDs from the Projects API if you don't have them
- [ ] **Update list response parsing** — unwrap the `.items` array from the envelope; extract `.total` and `.next_cursor` for pagination logic
- [ ] **Add pagination loop** — if you previously iterated over all tasks, implement cursor-based pagination using `next_cursor`
- [ ] **Test with a sandbox account** — verify each endpoint with the new v2 contract before pointing production traffic

---

## Upgrade Command

```bash
npm install @zrb/cli@latest
```

Or, depending on your package manager:

```bash
yarn add @zrb/cli@latest
pnpm add @zrb/cli@latest
```

After installing, run `zrb --version` to confirm v2 is active.
