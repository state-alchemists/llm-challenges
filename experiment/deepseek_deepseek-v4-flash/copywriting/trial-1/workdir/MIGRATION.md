# Zrb v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. Six breaking changes affect every existing v1 integration. This guide walks through each change with before/after examples, then provides a step-by-step migration checklist.

**Audience:** developers with a working v1 integration.

**References:** [v1 API spec](./v1_spec.md) · [v2 API spec](./v2_spec.md)

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | API paths | `/tasks` | `/v2/tasks` |
| 2 | Auth header | `X-Auth-Token: <api_key>` | `Authorization: Bearer <token>` |
| 3 | Task `id` type | integer (`42`) | UUID string (`"a1b2..."`) |
| 4 | Status field | `done` | `completed` |
| 5 | Create payload | `title` only | `title` + `project_id` (required) |
| 6 | List response | bare array | paginated envelope |

---

## 1. API paths now require the `/v2/` prefix

All endpoints moved under `/v2/`. Existing v1 paths will no longer resolve.

**Before (v1):**

```bash
curl -X GET https://api.zrb.example/tasks
curl -X POST https://api.zrb.example/tasks
curl -X GET https://api.zrb.example/tasks/42
```

**After (v2):**

```bash
curl -X GET https://api.zrb.example/v2/tasks
curl -X POST https://api.zrb.example/v2/tasks
curl -X GET https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

If your client stores a base URL or endpoint constants in one place, this is a single-location change. Watch out for hardcoded path strings scattered through the codebase.

---

## 2. Authentication now uses a Bearer token

The `X-Auth-Token` header is gone. Requests that still send it receive **HTTP 401 Unauthorized**.

**Before (v1):**

```bash
curl https://api.zrb.example/tasks \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**

```bash
curl https://api.zrb.example/v2/tasks \
  -H "Authorization: Bearer <your_api_token>"
```

Your old API key will not work as a token. Obtain a v2 token from the dashboard before you cut over, and update any shared clients, SDKs, or CI secrets that inject the header.

---

## 3. Task IDs changed from integer to UUID string

`id` is now a UUID string instead of an auto-incremented integer. This affects both response parsing and URL construction.

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

Practical implications:

- Do **not** parse `id` as a number — it will no longer be numeric.
- Store and pass IDs as strings, including in URL path segments: `GET /v2/tasks/{id}` now takes the UUID.
- Do not rely on ID ordering or range for assumptions (e.g., "latest task has the highest ID").
- If you persist task IDs locally (caches, foreign keys, analytics), you will need to migrate that stored data, since old integer IDs do not map 1:1 to the new UUIDs.

---

## 4. Task field `done` renamed to `completed`

The boolean status field is renamed in **both** request and response bodies. The v1 field is no longer accepted.

**Before (v1) — update request and response:**

```json
{
  "title": "Updated title",
  "done": true
}
```

```json
{
  "id": 42,
  "title": "Updated title",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — update request and response:**

```json
{
  "title": "Updated title",
  "completed": true
}
```

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Updated title",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Update your client's request builders, response deserializers/serializers, and any UI or domain models that read `task.done`.

---

## 5. Creating a task now requires `project_id`

`POST /v2/tasks` requires a `project_id` in the request body. Omitting it returns **HTTP 422 Unprocessable Entity**. v1 requests that send only `title` will fail.

**Before (v1):**

```json
{
  "title": "New task title"
}
```

**After (v2):**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Every create call site must supply a valid project ID. If you have existing tasks, plan a data backfill or a default project for legacy records. Note that the created task object (HTTP 201) now also carries `project_id` and a UUID `id` — see changes 3 and 4.

---

## 6. List endpoints return a paginated envelope

List responses are no longer a bare array. They now return an envelope with `items`, `total`, and a `next_cursor`. Use `?cursor=<next_cursor>` (and optionally `?limit=`, default 20) to page through results.

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

**After (v2) — paging through results:**

```bash
curl "https://api.zrb.example/v2/tasks?limit=20" \
  -H "Authorization: Bearer <your_api_token>"

curl "https://api.zrb.example/v2/tasks?cursor=cursor_xyz&limit=20" \
  -H "Authorization: Bearer <your_api_token>"
```

Consumers that assumed `response[0]`, iterated the array directly, or counted results by array length must switch to reading `items`, `total`, and following `next_cursor` until it is null/absent. If you have a "load everything" helper, replace it with a loop that chases cursors.

---

## What Did NOT Change

To save you re-reading the spec: `title` and `created_at` are unchanged, `GET /v2/tasks/{id}` still returns `404` for missing tasks, `POST` still returns `201` on success, `PUT` still accepts partial updates with all fields optional, and `DELETE /v2/tasks/{id}` still returns `204 No Content`. The new `limit` and `cursor` query parameters are optional, so a plain `GET /v2/tasks` is valid — it just returns page 1 of an envelope.

---

## Step-by-Step Migration Checklist

1. **Update the base URL.** Prefix all endpoint paths with `/v2/` (e.g., `https://api.zrb.example/v2/tasks`).
2. **Switch authentication.** Replace the `X-Auth-Token` header with `Authorization: Bearer <your_api_token>` and rotate credentials in every client, SDK, and CI secret. Verify old header requests now fail with 401.
3. **Treat IDs as strings.** Update deserializers so `id` parses as a string, update URL builders to interpolate UUIDs, and migrate any locally stored integer task IDs.
4. **Rename `done` → `completed`.** Update request builders, response deserializers/serializers, and domain models that reference the status field.
5. **Add `project_id` to create calls.** Update every `POST /v2/tasks` payload and handle the new 422 error for missing `project_id`. Backfill or assign a default project for existing data.
6. **Update list consumers.** Read `items` instead of the bare array, use `total` for counts, and implement cursor pagination (loop on `next_cursor`; optionally set `limit`).
7. **Update tests and fixtures.** Refresh mocks, fixtures, and golden JSON files to the v2 shapes (UUID `id`, `completed`, `project_id`, envelope responses).
8. **Deploy and smoke test.** Run one request per endpoint against a staging v2 environment: list (with paging), get, create (with and without `project_id`), update, and delete.

---

## Upgrade Command

Once your code is migrated, upgrade the Zrb CLI to v2:

```bash
pip install --upgrade "zrb>=2,<3"
```

If you installed Zrb through another package manager (npm, Homebrew, Docker image, etc.), run the equivalent update command for that channel.
