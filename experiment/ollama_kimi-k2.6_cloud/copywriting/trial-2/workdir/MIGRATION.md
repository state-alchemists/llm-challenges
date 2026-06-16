# Migrating from Zrb Task API v1 to v2

This guide walks you through the breaking changes between v1 and v2 of the Zrb Task API. You should already be familiar with v1 — the sections below highlight what to change and why.

## Table of Contents

- [Summary of Breaking Changes](#summary-of-breaking-changes)
- [Endpoint Prefix](#endpoint-prefix)
- [Authentication](#authentication)
- [Task ID Format](#task-id-format)
- [Renamed Field: `done` → `completed`](#renamed-field-done--completed)
- [Required `project_id` on Creation](#required-project_id-on-creation)
- [Paginated List Responses](#paginated-list-responses)
- [Migration Checklist](#migration-checklist)
- [Upgrade Command](#upgrade-command)

---

## Summary of Breaking Changes

| # | Change | Impact |
|---|--------|--------|
| 1 | All endpoints moved to `/v2/*` | Update every request URL |
| 2 | Auth header changed to `Authorization: Bearer …` | Update auth logic |
| 3 | Task `id` changed from `integer` to `UUID string` | Adjust storage, routing, and validation |
| 4 | Task field `done` renamed to `completed` | Update deserialization and UI |
| 5 | Creating a task now requires `project_id` | Supply `project_id` in create calls |
| 6 | List endpoints return a paginated envelope | Iterate with cursor instead of reading a bare array |

---

## Endpoint Prefix

All task endpoints are now prefixed with `/v2/`. Requests to the old paths will **not** be routed.

**Before (v1):**

```bash
curl https://api.zrb.example.com/tasks
curl https://api.zrb.example.com/tasks/42
```

**After (v2):**

```bash
curl https://api.zrb.example.com/v2/tasks
curl https://api.zrb.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## Authentication

The custom `X-Auth-Token` header has been replaced by a standard Bearer token scheme. Sending `X-Auth-Token` will result in an HTTP `401` response.

**Before (v1):**

```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.example.com/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.example.com/v2/tasks
```

---

## Task ID Format

Task `id` is now a UUID string instead of an integer. This affects:

- Database storage types
- Route parameters (they are strings now)
- Client-side validation (e.g., regexes expecting digits)

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

## Renamed Field: `done` → `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`. Using the old name in payloads or relying on it in responses will silently break logic.

**Before (v1):**

```json
// Request
PUT /tasks/42
{
  "done": true
}

// Response
{
  "id": 42,
  "title": "Write tests",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2):**

```json
// Request
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{
  "completed": true
}

// Response
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

## Required `project_id` on Creation

Creating a task now requires a `project_id` in the request body. Omitting it returns HTTP `422`.

**Before (v1):**

```bash
curl -X POST https://api.zrb.example.com/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

**After (v2):**

```bash
curl -X POST https://api.zrb.example.com/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

## Paginated List Responses

`GET /v2/tasks` no longer returns a bare JSON array. It returns a paginated envelope containing an `items` array, a `total` count, and a `next_cursor` for fetching the next page.

**Before (v1):**

```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.example.com/tasks
```

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.example.com/v2/tasks?limit=20"
```

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6-7890-...", "title": "Ship v2", "completed": true, "project_id": "proj_def456", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, pass `?cursor=<next_cursor>`.

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.example.com/v2/tasks?limit=20&cursor=cursor_xyz"
```

---

## Migration Checklist

Use this checklist to roll out the upgrade safely.

1. **Dependencies**
   - [ ] Upgrade SDK / CLI to the latest v2 release.
   - [ ] Regenerate client stubs from the v2 OpenAPI spec if applicable.

2. **Authentication**
   - [ ] Replace `X-Auth-Token` with `Authorization: Bearer <token>` in all outgoing requests.
   - [ ] Rotate or regenerate API tokens if the old key format is incompatible.

3. **Endpoints**
   - [ ] Prefix all task URLs with `/v2/`.
   - [ ] Audit reverse proxies, load balancers, and API gateways for path rewrites.

4. **Data Types**
   - [ ] Migrate stored task IDs from integers to UUID strings.
   - [ ] Update database columns, cache keys, and foreign-key references.
   - [ ] Relax or replace client-side numeric-ID validation.

5. **Payload Fields**
   - [ ] Rename every occurrence of `done` to `completed` in request bodies, response parsing, and UI bindings.
   - [ ] Add `project_id` to all task-creation payloads.
   - [ ] Backfill existing tasks with a `project_id` if migrating historical data.

6. **Pagination**
   - [ ] Replace bare-array list handling with envelope-aware logic (`items`, `next_cursor`).
   - [ ] Implement cursor-based iteration for large lists.
   - [ ] Respect the default `limit` of 20 and override only when necessary.

7. **Testing**
   - [ ] Run integration tests against the v2 sandbox.
   - [ ] Verify all CRUD flows, list pagination, and error responses (e.g., 401 for old auth, 422 for missing `project_id`).

8. **Deploy**
   - [ ] Deploy v2-compatible clients before switching traffic to v2 backends.
   - [ ] Monitor error rates for 401s and 422s immediately after cutover.

---

## Upgrade Command

Install or upgrade the Zrb CLI to v2:

```bash
npm install -g @zrb/cli@latest
```
