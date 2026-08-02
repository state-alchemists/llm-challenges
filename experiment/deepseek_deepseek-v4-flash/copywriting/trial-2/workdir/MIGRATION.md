# Zrb CLI v2 Migration Guide

Zrb v2 ships with six breaking changes to the Task API. This guide walks
experienced v1 developers through each one, shows the before/after for every
change, and ends with a step-by-step checklist. Plan for a coordinated
rollout: the auth header change means v1 clients receive `401` from v2
servers, so client and server should move together.

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | URL prefix | `/tasks` | `/v2/tasks` |
| 2 | Auth header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Field rename | `done` | `completed` |
| 5 | Create requires | `title` only | `title` + `project_id` |
| 6 | List response | bare array | paginated envelope |

## 1. All Endpoints Move Under `/v2/`

Every endpoint is now prefixed with `/v2/`. This applies to list, get,
create, update, and delete.

**Before (v1):**

```text
GET    /tasks
GET    /tasks/{id}
POST   /tasks
PUT    /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```text
GET    /v2/tasks
GET    /v2/tasks/{id}
POST   /v2/tasks
PUT    /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

Update your base URL, route registrations, and any hard-coded paths. If you
build URLs from a base constant, change it once and the rest follows.

## 2. Authentication Header Changed

The `X-Auth-Token` header is gone. Authenticate with a standard Bearer
token in the `Authorization` header. Requests that still send
`X-Auth-Token` receive `HTTP 401`.

**Before (v1):**

```text
X-Auth-Token: <your_api_key>
```

**After (v2):**

```text
Authorization: Bearer <your_api_token>
```

Update your HTTP client, SDK wrapper, and any stored configuration. Make
sure token rotation and credential storage follow your existing secrets
process — this is a new token namespace, not the v1 key renamed.

## 3. Task `id` Is Now a UUID String

Task identifiers changed from auto-assigned integers to UUID strings.
This affects the `id` field in every task object and the `{id}` path
parameter in get, update, and delete calls.

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

Treat ids as opaque strings everywhere: stop parsing them as integers,
stop assuming sort order or monotonicity, and validate UUID format instead
of numeric range. Any database column or cache key typed as an integer must
be widened to a string/UUID column.

## 4. `done` Renamed to `completed`

The boolean completion flag is now `completed`. The old `done` field no
longer exists in responses, and sending `done` in a `PUT` body no longer
updates the task.

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

Search your codebase for `.done`, `["done"]`, and `done:` and rename them
all to `completed`. Do not ship a compatibility shim that maps between the
two — clients that send `done` will silently fail to update.

## 5. Creating a Task Now Requires `project_id`

`POST /v2/tasks` now requires `project_id` in the request body. Omitting
it returns `HTTP 422`. Decide which project a new task belongs to before
you call the API.

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

Thread the project through your UI, CLI, and import scripts. If a project
is selected in your app, use it; otherwise add the field to the task
creation form and treat a missing selection as a validation error.

## 6. List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope
with `items`, `total`, and `next_cursor`, and accepts `cursor` and
`limit` query parameters (`limit` defaults to 20).

**Before (v1):**

```json
GET /tasks
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**

```json
GET /v2/tasks?limit=20
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Paginate through all results:**

```json
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

Rewrite list consumers to read `items`, and loop on `next_cursor` until it
is null/empty instead of assuming one response holds everything. Update any
code that indexes the response as an array (`response[0]`, `.map`, `len()`).

## Migration Checklist

Work through these in order:

- [ ] 1. Read the v2 spec and diff your call sites against each of the six
      changes above.
- [ ] 2. Replace `X-Auth-Token` with `Authorization: Bearer` in your HTTP
      client and configuration, and issue new tokens if required.
- [ ] 3. Prefix every endpoint with `/v2/` (base URL or per-route).
- [ ] 4. Migrate stored task ids from integer to UUID string and update
      path parameters and cache keys.
- [ ] 5. Rename every `done` field to `completed` in requests and
      response parsing.
- [ ] 6. Add `project_id` to task creation payloads and UI flows.
- [ ] 7. Rewrite list handling to consume the paginated envelope and loop
      on `next_cursor`.
- [ ] 8. Update tests and mocks to v2 shapes; add a 401 check for the old
      auth header and a 422 check for a missing `project_id`.
- [ ] 9. Run the full suite against a v2 endpoint, then deploy client and
      server together.

## Upgrade to v2

Verify the install once you are on the new client (`zrb --version`), then
upgrade:

```bash
pip install --upgrade zrb
```

If you manage the CLI with pipx instead:

```bash
pipx upgrade zrb
```
