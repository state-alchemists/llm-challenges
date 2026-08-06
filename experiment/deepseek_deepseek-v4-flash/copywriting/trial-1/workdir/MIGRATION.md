# Zrb Task API — v2 Migration Guide

This guide documents every breaking change between the v1 and v2 Task APIs. v2 introduces projects, cursor-based pagination, and Bearer-token authentication. Work through the sections in order — each one names the change, the failure mode, and a before/after example.

Unchanged in v2: the `title` and `created_at` fields, the `GET /tasks/{id}` → 404 behavior, `POST` returning HTTP 201, `PUT` accepting partial updates, and `DELETE` returning 204.

## Breaking Changes at a Glance

| # | Change | Failure mode |
|---|--------|--------------|
| 1 | All endpoints moved under `/v2/` | Old paths return 404 |
| 2 | `X-Auth-Token` replaced by `Authorization: Bearer` | Requests with the old header return 401 |
| 3 | Task `id` changed from integer to UUID string | Type errors, broken URLs, failed comparisons |
| 4 | `done` renamed to `completed` | Writes ignored, reads miss the flag |
| 5 | `project_id` is required on create | Create requests without it return 422 |
| 6 | List endpoints return a paginated envelope, not a bare array | Parser errors; data truncated at 20 items |

## 1. Endpoints Are Now Prefixed with `/v2/`

Every v1 endpoint moved under the `/v2/` prefix. v1 paths no longer exist and return HTTP 404.

**Before:**
```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.example.com/tasks
```

**After:**
```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.example.com/v2/tasks
```

Endpoint mapping:

| v1 | v2 |
|----|----|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

Update base URLs, path constants, and any hardcoded route strings.

## 2. Authentication Header Changed to Bearer Token

The header changed from `X-Auth-Token` to `Authorization: Bearer`. Requests sent with the old header receive HTTP 401 — the old header is not accepted as an alias. v2 tokens may be different values from v1 keys, so issue or retrieve new credentials before migrating.

**Before:**
```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.example.com/tasks
```

**After:**
```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.example.com/v2/tasks
```

## 3. Task IDs Changed from Integer to UUID String

`id` is now a UUID string instead of an auto-assigned integer. IDs can no longer be incremented, compared numerically, or stored in integer columns. Update client models, database schema, caches, and anything that formats or interpolates an ID into a URL.

**Before:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.example.com/tasks/42
```

**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## 4. `done` Renamed to `completed`

The boolean field is now `completed`. The change applies in both directions: request bodies must send `completed`, and response parsing must read `completed`. Anything still writing `done` is silently ignored.

**Before:**
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

**After:**
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

## 5. `project_id` Is Now Required on Create

`POST /v2/tasks` requires a `project_id` field. Omitting it returns HTTP 422. Create the project first (or look up an existing one) and include its ID in every create request.

**Before:**
```json
{
  "title": "New task title"
}
```

**After:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

## 6. List Endpoints Return a Paginated Envelope

List endpoints no longer return a bare array. They return an envelope with `items`, `total`, and `next_cursor`, and default to 20 items per page (`limit`). Clients must read `items` and follow `next_cursor` until it is empty — otherwise they see at most the first page.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "2024-01-15T10:30:00Z"},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "2024-01-15T10:30:00Z"}
]
```

**After:**
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

```js
let cursor;
do {
  const url = new URL("https://api.example.com/v2/tasks");
  url.searchParams.set("limit", "20");
  if (cursor) url.searchParams.set("cursor", cursor);
  const page = await (await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  })).json();
  for (const task of page.items) {
    // handle task
  }
  cursor = page.next_cursor;
} while (cursor);
```

## Migration Checklist

- [ ] 1. Upgrade the client/SDK to a v2-compatible release (see Upgrade below).
- [ ] 2. Replace `X-Auth-Token` with `Authorization: Bearer` in every request — code, configs, scripts, and CI jobs. Issue new v2 tokens.
- [ ] 3. Prefix all endpoint paths with `/v2/`; update base URLs and hardcoded routes.
- [ ] 4. Change task ID handling to strings: update schemas, DB columns, caches, and URL builders.
- [ ] 5. Rename `done` to `completed` in all request bodies and response parsing.
- [ ] 6. Add `project_id` to every create call; create or resolve the project first.
- [ ] 7. Rewrite list consumers to parse the envelope and follow `next_cursor`; account for the 20-item default `limit`.
- [ ] 8. Test: run the suite against v2, verify the 401/404/422 error paths, then deploy to staging before production.

## Upgrade

```bash
pip install --upgrade "zrb>=2.0.0,<3.0.0"
```
