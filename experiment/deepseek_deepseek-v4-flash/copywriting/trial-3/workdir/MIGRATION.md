# Zrb v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. It ships with **six breaking changes** to the task API. Every v1 client — scripts, SDKs, CI pipelines, and stored integrations — must be updated before you can move to v2.

This guide assumes you already use v1. For each breaking change you get the v1 behavior, the v2 replacement, and what to update in your code. A step-by-step checklist and the upgrade command are at the end.

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | API path prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication | `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |
| 3 | Task ID type | integer (`42`) | UUID string (`"a1b2c3d4-…"`) |
| 4 | Field rename | `done` | `completed` |
| 5 | Create requirement | `title` only | `title` + `project_id` (required) |
| 6 | List response shape | bare array | paginated envelope (`items`, `total`, `next_cursor`) |

## 1. All endpoints move under `/v2/`

Every endpoint is now prefixed with `/v2/`. Old paths return `404`.

**Before (v1):**

```
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

**What to update:** the base path in every request, any hardcoded URLs, SDK client configuration, and any stored links or webhooks that reference `/tasks/...`.

## 2. Authentication: API key → Bearer token

The `X-Auth-Token` header is gone. Requests that still send it receive **HTTP 401**.

**Before (v1):**

```
X-Auth-Token: <your_api_key>
```

**After (v2):**

```
Authorization: Bearer <your_api_token>
```

**Before (v1):**

```bash
curl "$API_BASE/tasks" \
  -H "X-Auth-Token: $API_KEY"
```

**After (v2):**

```bash
curl "$API_BASE/v2/tasks" \
  -H "Authorization: Bearer $API_TOKEN"
```

**What to update:** every client that sets the auth header — libraries, tests, and any hardcoded `X-Auth-Token` in configs or CI secrets. Issue the v2 token in advance; the old header is rejected outright with `401`.

## 3. Task IDs: integers become UUID strings

`id` changes from an integer to a UUID string. `GET`, `PUT`, and `DELETE` all take the UUID. Stored integer IDs are no longer valid.

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

**What to update:** treat `id` as an opaque string — no integer casts, no arithmetic, no relying on IDs increasing over time. If you persisted v1 integer IDs (databases, URLs, cache keys), re-fetch and re-map them to the v2 UUIDs before cutting over.

## 4. Field rename: `done` → `completed`

The task status field is renamed. v1 `done` is v2 `completed`. The v2 update endpoint expects `completed`; sending `done` no longer sets status.

**Before (v1) request:**

```json
{ "title": "Write tests", "done": true }
```

**After (v2) request:**

```json
{ "title": "Write tests", "completed": true }
```

**Before (v1) response:**

```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2) response:**

```json
{ "id": "a1b2c3d4-…", "title": "Write tests", "completed": false }
```

**What to update:** all request bodies and all response parsing that reads `done` — model classes, serializers, UI bindings, and tests. Search your request/response handling for `done` and replace it with `completed`.

## 5. Create requires `project_id`

Creating a task now requires `project_id`. Omitting it returns **HTTP 422**.

**Before (v1):**

```
POST /tasks
```

```json
{ "title": "New task title" }
```

**After (v2):**

```
POST /v2/tasks
```

```json
{ "title": "New task title", "project_id": "proj_abc123" }
```

**What to update:** every create flow must resolve a project first — add a project selector to UIs and CLIs, and pass a valid `project_id` from configuration or an earlier lookup in scripts. Add `422` handling to your error paths.

## 6. List responses are paginated envelopes

List endpoints no longer return a bare array. They return an envelope with `items`, `total`, and `next_cursor`. Pagination is cursor-based; the default page size is 20.

**Before (v1):**

```json
[
  { "id": 1, "title": "Buy milk", "done": false },
  { "id": 2, "title": "Ship v1", "done": true }
]
```

**After (v2):**

```json
{
  "items": [
    { "id": "a1b2c3d4-…", "title": "Buy milk", "completed": false },
    { "id": "e5f6a1b2-…", "title": "Ship v1", "completed": true }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Before (v1) — one call, everything back:**

```bash
curl "$API_BASE/tasks" -H "X-Auth-Token: $API_KEY"
```

**After (v2) — page with the cursor:**

```bash
curl "$API_BASE/v2/tasks?limit=20" -H "Authorization: Bearer $API_TOKEN"
curl "$API_BASE/v2/tasks?limit=20&cursor=cursor_xyz" -H "Authorization: Bearer $API_TOKEN"
```

**What to update:** iterate pages by passing `next_cursor` as the `cursor` query param until it is empty; never assume all results arrive in one response. `limit` caps each page (default 20). Update list parsing to read `items`, and treat `total` as the matched count.

## What Hasn't Changed

- `title` and `created_at` keep their names and types.
- `GET /v2/tasks/{id}` still returns the task or `404`.
- `POST /v2/tasks` returns `201` with the created task.
- `DELETE /v2/tasks/{id}` returns `204 No Content`.
- Update accepts all fields as optional.

## Migration Checklist

Follow these in order:

1. **Upgrade the CLI** to v2 (command at the end of this guide).
2. **Issue and store v2 tokens.** Replace `X-Auth-Token` with `Authorization: Bearer <token>` in every client, config, and CI secret.
3. **Prefix every path with `/v2/`.** Sweep code, SDK config, and stored URLs for `/tasks` and update them.
4. **Re-map persisted IDs.** Replace stored integer task IDs with v2 UUIDs (re-fetch from `GET /v2/tasks` if needed).
5. **Rename `done` → `completed`** in all request bodies, response parsing, models, and tests.
6. **Add `project_id` to every create call** and handle the `422` response.
7. **Rework list handling for the envelope** — read `items`, page with `next_cursor`, respect `limit`.
8. **Update fixtures and mocks** to v2 shapes (UUIDs, `completed`, envelope).
9. **Test against staging**: verify auth (`401`), create without `project_id` (`422`), pagination across multiple pages, and the `404` path.
10. **Cut over** — deploy the updated clients, then retire v1 usage.

## Upgrade to v2

```bash
pip install --upgrade zrb
```

Installed via `pipx` instead? Use `pipx upgrade zrb`. The exact command varies with your installation method — upgrade the same way you installed v1.
