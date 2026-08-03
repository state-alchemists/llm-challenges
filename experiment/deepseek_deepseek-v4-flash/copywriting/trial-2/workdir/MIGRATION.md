# Zrb CLI v2 Migration Guide

This guide walks you from the v1 Task API (`v1_spec.md`) to the v2 API
(`v2_spec.md`). It is written for teams already shipping against v1.

**There is no backward compatibility.** v2 changes the auth scheme, the
endpoint paths, the task object shape, and the list response format. Requests
that still speak v1 will fail: old auth headers get `401`, un-prefixed paths
no longer resolve, and old payloads are rejected.

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication | `X-Auth-Token: <api_key>` | `Authorization: Bearer <token>` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Completion field | `done` | `completed` |
| 5 | Task creation | `title` only | `title` + required `project_id` |
| 6 | List responses | bare array | paginated envelope |

Each change is detailed below with before/after examples.

## Breaking Changes

### 1. All endpoints are now under `/v2/`

Every endpoint moved from `/tasks` to `/v2/tasks`. There is no redirect and no
v1-compatible path — update every URL your client builds.

**Before (v1):**

```bash
curl https://api.example.com/tasks
curl https://api.example.com/tasks/42
```

**After (v2):**

```bash
curl https://api.example.com/v2/tasks
curl https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

### 2. Authentication now uses Bearer tokens

The `X-Auth-Token` header is gone. Authenticate with an `Authorization:
Bearer` header instead. Requests sent with `X-Auth-Token` receive **HTTP 401**.

**Before (v1):**

```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.example.com/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.example.com/v2/tasks
```

Issue your new v2 tokens before cutover so the migration does not depend on
rotating credentials mid-release.

### 3. Task `id` is now a UUID string, not an integer

Task identifiers changed from auto-incremented integers to UUID strings. They
appear in every task object and in the path of `GET`, `PUT`, and `DELETE`
requests. Treat them as opaque strings: stop parsing, casting, or ordering by
`id`, and do not build URLs from cached v1 numeric ids.

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

If your client stored v1 integer ids, re-fetch or re-map them before using them
in v2 requests — the numeric value is no longer a valid identifier.

### 4. `done` is renamed to `completed`

The boolean completion field is now `completed` on reads and writes. `done`
is no longer part of the API.

**Before (v1):**

```bash
curl -X PUT https://api.example.com/tasks/42 \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "Updated title", "done": true}'
```

**After (v2):**

```bash
curl -X PUT https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "Updated title", "completed": true}'
```

Search your codebase for `done` in task payloads and response parsing — the
rename applies everywhere the field is read or written.

### 5. `project_id` is required when creating tasks

Task creation now requires `project_id`. Omitting it returns **HTTP 422**.
The field also appears on every task object returned by the API, so response
parsers must accept it.

**Before (v1):**

```bash
curl -X POST https://api.example.com/tasks \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

**After (v2):**

```bash
curl -X POST https://api.example.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

Collect the `project_id` values your workflows need before you ship — every
create call must now carry one.

### 6. List endpoints return a paginated envelope, not a bare array

`GET /v2/tasks` no longer returns an array. It returns `{ "items", "total",
"next_cursor" }`, with `limit` (default 20) and `cursor` query parameters.

**Before (v1):**

```bash
curl https://api.example.com/tasks
```

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**

```bash
curl "https://api.example.com/v2/tasks?limit=20"
```

```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Iterate pages by passing `?cursor=<next_cursor>` and stop when the API returns
no further cursor. A typical client loop:

```bash
cursor=""
while :; do
  url="https://api.example.com/v2/tasks?limit=100${cursor:+&cursor=$cursor}"
  page=$(curl -s -H "Authorization: Bearer $TOKEN" "$url")
  # process "$page" | jq '.items[]' ...
  cursor=$(echo "$page" | jq -r '.next_cursor')
  [ -z "$cursor" ] || [ "$cursor" = "null" ] && break
done
```

Any code that mapped or iterated the old array directly must be updated to
read `items`, and any code that assumed "all results in one response" must now
handle pagination.

## What Did Not Change

- `title` and `created_at` keep their meaning and format.
- `PUT` still accepts all-optional bodies.
- `POST` still returns `201` with the created task; `GET` still returns `404`
  when a task is not found; `DELETE` still returns `204 No Content`.

## Migration Checklist

1. **Upgrade the CLI** — run the upgrade command at the bottom of this guide
   and confirm `zrb --version` reports v2.
2. **Issue v2 tokens** — generate Bearer tokens for every environment
   (dev, staging, prod) and store them in your secret manager.
3. **Replace auth headers** — swap `X-Auth-Token` for
   `Authorization: Bearer <token>` in every client and integration test.
4. **Prefix all endpoints** — update every URL from `/tasks` to `/v2/tasks`
   (list, get, create, update, delete).
5. **Migrate task ids** — stop treating `id` as an integer; re-map any stored
   v1 ids, and make URL construction use the UUID strings returned by v2.
6. **Rename `done` → `completed`** — update all request payloads and all
   response-parsing code; grep for `done` across task-handling modules.
7. **Add `project_id` to creates** — add the required field to every
   `POST /v2/tasks` call and to any fixtures or seeds.
8. **Rewrite list handling** — parse `items`, `total`, and `next_cursor`;
   add a cursor loop for pagination; respect `limit` (default 20).
9. **Smoke-test each endpoint** — auth returns `200` not `401`; create returns
   `201` not `422`; list returns the envelope; update round-trips `completed`.
10. **Deploy and monitor** — ship the client changes together, then watch for
    `401` (stale auth), `404` (un-prefixed or numeric-id paths), and `422`
    (missing `project_id`).

## Upgrade to v2

```bash
pip install --upgrade zrb
```

Installed via pipx instead? Run `pipx upgrade zrb`. Using the install script
or Docker, follow the same channel you used for v1 — then verify with
`zrb --version`.
