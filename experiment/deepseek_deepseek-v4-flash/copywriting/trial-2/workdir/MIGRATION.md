# Zrb CLI v2 — Migration Guide

Zrb v2 introduces projects, paginated list endpoints, and stricter authentication. This guide walks experienced v1 developers through every breaking change, with before/after examples, and ends with a step-by-step migration checklist.

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | API path prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token: <api_key>` | `Authorization: Bearer <token>` |
| 3 | Task `id` type | integer (`42`) | UUID string (`"a1b2..."`) |
| 4 | Completion field | `done` | `completed` |
| 5 | Create requirement | `title` only | `title` + `project_id` (required) |
| 6 | List response | bare array | paginated envelope |

---

## 1. All Endpoints Are Now Prefixed with `/v2/`

Every endpoint moved from `/tasks` to `/v2/tasks`. Requests to the old paths will not resolve; update all base URLs, path constants, and client configuration.

**Before (v1):**

```bash
curl -X GET https://api.example.com/tasks \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**

```bash
curl -X GET https://api.example.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>"
```

---

## 2. Authentication Header Changed

The `X-Auth-Token` header is replaced by the standard Bearer token scheme. Any request that still sends `X-Auth-Token` will receive **HTTP 401 Unauthorized**.

**Before (v1):**

```bash
curl -X GET https://api.example.com/tasks \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**

```bash
curl -X GET https://api.example.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>"
```

Update any SDK constructors, HTTP client defaults, and hardcoded headers.

---

## 3. Task `id` Changed from Integer to UUID String

Task identifiers are now UUID strings instead of integers. Treat `id` as an opaque string — do not parse it as a number, increment it, or store it in an integer column.

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

Consequences to check in your code:

- Fetch by ID: `GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890` (not `/v2/tasks/42`).
- Any URL-building that interpolated the integer ID now needs the full UUID string.
- Database columns storing task IDs must widen to a string type (e.g., `TEXT` or `VARCHAR(36)`); re-key foreign references.

---

## 4. Task Field `done` Renamed to `completed`

The boolean completion flag is now `completed`. Old `done` keys will be ignored — or rejected, depending on the endpoint — so reads return stale data and writes silently no-op unless renamed.

**Before (v1):**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**

```json
{
  "title": "Updated title",
  "completed": true
}
```

Update field mappings in serializers, ORM models, and frontend components. Note that the task response also includes `project_id` (see next section).

---

## 5. Creating a Task Now Requires `project_id`

`POST /v2/tasks` requires `project_id`. Omitting it returns **HTTP 422 Unprocessable Entity**. You must first create or obtain a project and pass its ID on every task creation.

**Before (v1):**

```bash
curl -X POST https://api.example.com/tasks \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**

```bash
curl -X POST https://api.example.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

Update any task-creation code paths — bulk importers, tests, and scripts — to resolve a `project_id` before creating tasks.

---

## 6. List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope with `items`, `total`, and `next_cursor`. Pagination is cursor-based: pass `?cursor=<next_cursor>` to fetch the next page. `limit` controls page size and defaults to 20.

**Before (v1):**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**

```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Before (v1)** — iterate a bare array:

```bash
curl -s https://api.example.com/tasks -H "X-Auth-Token: <your_api_key>"
```

**After (v2)** — follow the cursor:

```bash
# page 1
curl -s "https://api.example.com/v2/tasks?limit=20" \
  -H "Authorization: Bearer <your_api_token>"

# next page
curl -s "https://api.example.com/v2/tasks?cursor=cursor_xyz&limit=20" \
  -H "Authorization: Bearer <your_api_token>"
```

Update list-handling code to read `items` instead of the top-level array, and loop until `next_cursor` is null/absent.

---

## Step-by-Step Migration Checklist

1. **Upgrade to Zrb v2** (see upgrade command below) and verify the installed version.
2. **Update authentication** — replace `X-Auth-Token` with `Authorization: Bearer <token>` in every client, SDK, and test fixture. Confirm no request still sends the old header.
3. **Prefix all paths with `/v2/`** — update base URLs and route constants; grep for `"/tasks"` and other v1 paths.
4. **Treat `id` as a UUID string** — stop integer arithmetic on IDs, widen database columns, and rebuild URL paths with the full UUID.
5. **Rename `done` → `completed`** in request bodies, response parsing, and model mappings.
6. **Supply `project_id` on creation** — resolve a project first and add it to every `POST /v2/tasks` payload; handle the 422 error path.
7. **Handle the paginated envelope** — read `items`, use `next_cursor`/`limit` for paging, and update any consumers that assumed a bare array.
8. **Update persistence** — migrate stored task IDs and `done` flags in any database, cache, or local store.
9. **Run your test suite** — fix failures against v2 error codes (401 for auth, 422 for missing `project_id`, 404 for unknown UUIDs).
10. **Deploy** — roll out clients and services together; v1 endpoints are not part of v2.

## Upgrading

Install the latest version of the Zrb CLI:

```bash
pip install --upgrade zrb
```

If you installed Zrb with pipx, use:

```bash
pipx upgrade zrb
```

Verify the upgrade succeeded, then walk the checklist above before switching traffic to v2.
