# Zrb CLI v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. All endpoints and resource representations have changed, and **v1 will be sunset 90 days after the v2 stable release**.

This guide walks through every breaking change. If you are already using v1, read each section and apply the checklist at the end.

---

## At a Glance: All Breaking Changes

| # | Area | v1 | v2 |
|---|------|----|----|
| 1 | URL prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task ID type | integer | UUID string |
| 4 | Task completion field | `done` | `completed` |
| 5 | Create task body | `title` only | `title` + `project_id` (required) |
| 6 | List response format | bare array | paginated envelope |

---

## 1. URL Base Path

All endpoints are now prefixed with `/v2/`. Requests to the old paths return `404`.

**Before (v1):**

```bash
curl https://api.zrb.dev/tasks
curl https://api.zrb.dev/tasks/42
curl -X POST https://api.zrb.dev/tasks
```

**After (v2):**

```bash
curl https://api.zrb.dev/v2/tasks
curl https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X POST https://api.zrb.dev/v2/tasks
```

Update your client's base URL and any endpoint path templates.

---

## 2. Authentication Header

The authentication method changed from a custom header to the standard Bearer token scheme. Requests using the old header will receive `HTTP 401`.

**Before (v1):**

```http
X-Auth-Token: sk_live_abc123
```

**After (v2):**

```http
Authorization: Bearer zb_a1b2c3d4e5f6g7h8i9j0
```

**cURL examples:**

```bash
# v1
curl -H "X-Auth-Token: sk_live_abc123" https://api.zrb.dev/tasks

# v2
curl -H "Authorization: Bearer zb_a1b2c3d4e5f6g7h8i9j0" https://api.zrb.dev/v2/tasks
```

Generate new tokens in the Zrb Dashboard under **Settings > API Tokens**. v1 API keys will not work with v2.

---

## 3. Task ID: Integer → UUID String

Task IDs are now UUID v4 strings instead of auto-incrementing integers. This affects the `id` field in all responses and the URL parameter for single-resource endpoints.

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

**Impact:**

- **GET / DELETE by ID** — you must now pass the UUID string.
- **Local storage** — if you cache task IDs as integers, migrate to string storage. UUIDs are 36 characters and will not fit int columns.
- **Dependent references** — any system that joins on or displays task IDs will need a schema update. The UUID format is backwards-incompatible by design.
- **Sorting** — UUIDs do not sort chronologically. Use `created_at` for ordering.

> **Tip:** Run a one-time migration to map old integer IDs to their new UUIDs. The v2 API returns a `created_at` timestamp you can use as the join key, or use the `/v2/migrate/id-map` endpoint (see docs) for a bulk mapping export.

---

## 4. Field Rename: `done` → `completed`

The task completion field has been renamed. The v2 API **will not return or accept** `done`.

**Before (v1) — request and response:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — request and response:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Before (v1) — updating a task:**

```bash
curl -X PUT https://api.zrb.dev/tasks/42 \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: sk_live_abc123" \
  -d '{"done": true}'
```

**After (v2) — updating a task:**

```bash
curl -X PUT https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer zb_a1b2c3d4e5f6g7h8i9j0" \
  -d '{"completed": true}'
```

Search your codebase for all references to `done` in relation to tasks and replace them with `completed`.

---

## 5. `project_id` Required on Task Creation

Every task must now belong to a project. The `project_id` field is required when creating a task. Omitting it returns `HTTP 422 Unprocessable Entity`.

**Before (v1):**

```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: sk_live_abc123" \
  -d '{"title": "Write tests"}'
```

**After (v2):**

```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer zb_a1b2c3d4e5f6g7h8i9j0" \
  -d '{"title": "Write tests", "project_id": "proj_abc123"}'
```

**What to do:**

1. If you don't already use projects, list available projects via `GET /v2/projects` (or create one via `POST /v2/projects`).
2. Decide on a default project for any automated workflows that create tasks without a project context. Hard-code a project ID or make it configurable.
3. Update your create-task flows to include `project_id` in the request body.

---

## 6. List Response Format: Paginated Envelope

List endpoints no longer return a bare array. v2 wraps results in a paginated envelope with `items`, `total`, and `next_cursor`.

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
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "created_at": "..."},
    {"id": "e5f6a7b8-...", "title": "Ship v1", "completed": true, "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Client code impact:**

```python
# v1 — iterate the array directly
tasks = response.json()
for task in tasks:
    print(task["title"])

# v2 — unwrap the envelope
body = response.json()
tasks = body["items"]
for task in tasks:
    print(task["title"])
```

**Pagination loop (v2):**

```python
cursor = None
while True:
    params = {"limit": 20}
    if cursor:
        params["cursor"] = cursor
    resp = client.get("/v2/tasks", params=params)
    body = resp.json()
    for task in body["items"]:
        process(task)
    cursor = body.get("next_cursor")
    if not cursor:
        break
```

The default page size is 20. Pass `?limit=<N>` to adjust (max 100).

---

## Migration Checklist

Complete these steps in order. Tick each off as you go.

- [ ] **Generate new API tokens.** Log into the Zrb Dashboard and create Bearer tokens for each environment (dev, staging, production). Save the old `X-Auth-Token` values — you will need them to re-link resources if you run the ID mapping migration later.
- [ ] **Update the base URL in all clients.** Change every endpoint path from `/tasks` to `/v2/tasks`. This is the simplest change to miss and the first to cause `404` errors.
- [ ] **Replace `X-Auth-Token` with `Authorization: Bearer`.** Update HTTP client configuration, curl commands, and any SDK initialization. Remember to also update request header logic in tests, CI scripts, and documentation.
- [ ] **Map task ID storage.** If you store task IDs in a database, add a `uuid VARCHAR(36)` column and run a migration script. Use the `/v2/migrate/id-map` endpoint or join on `created_at` to build the mapping.
- [ ] **Rename `done` to `completed`.** Sweep your codebase for every read, write, and display of the task completion field. Update serialization/deserialization logic, form bindings, UI components, and test fixtures. The change applies to both request and response payloads.
- [ ] **Assign a project to every task creation path.** Identify every call site that creates a task. If users or workflows do not currently provide a project context, choose a default project and hard-code its ID or add a configuration key. Update request bodies to include `project_id`.
- [ ] **Unwrap list responses.** Change all code that reads list endpoint responses to access `body["items"]` instead of treating the response as the array directly. Add pagination-aware iteration where needed.
- [ ] **Test against a staging environment.** Run your full integration test suite against the v2 API before deploying to production. Verify that every CRUD operation works, auth succeeds, and pagination returns complete data.
- [ ] **Sunset v1 references.** Remove v1 base URLs, old tokens, and any dead code paths after you have confirmed v2 is stable in production.

---

## Upgrade Command

```bash
pip install --upgrade zrb
```

After upgrading, verify the version:

```bash
zrb --version
# Expected: zrb 2.x.x
```

If you use a package manager other than pip (brew, npm, apt), see the [Zrb installation docs](https://zrb.dev/docs/install) for the v2 install command for your platform.
