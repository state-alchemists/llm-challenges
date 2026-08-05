# Zrb CLI v2 Migration Guide

Zrb CLI v2 introduces projects, paginated list endpoints, and stricter authentication, and it breaks the v1 API in six places. If you are already on v1, plan a coordinated change: every request, stored ID, and list consumer must be updated before you can point a client at v2.

This guide walks through each breaking change with before/after examples, then closes with a migration checklist and the upgrade command. The [v1 spec](v1_spec.md) and [v2 spec](v2_spec.md) are the authoritative references. Unchanged behavior: `title` and `created_at` keep their types and meanings, `GET /v2/tasks/{id}` still returns 404 for unknown tasks, and `DELETE /v2/tasks/{id}` still returns 204.

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | All endpoints prefixed with `/v2/` | Every URL must change |
| 2 | Auth header `X-Auth-Token` → `Authorization: Bearer` | Every request must change; v1 keys stop working |
| 3 | Task `id`: integer → UUID string | IDs are no longer numeric; stored ids must be re-keyed |
| 4 | Field `done` renamed to `completed` | Every read and write of the field changes |
| 5 | `project_id` required on create | Create calls without it fail with HTTP 422 |
| 6 | Lists return a paginated envelope | List responses change shape entirely |

## 1. Endpoint Prefix: `/v2/`

Every endpoint is now mounted under `/v2`. The v1 un-prefixed paths are not served, so requests to `https://api.zrb.dev/tasks` no longer resolve.

```bash
# v1
curl https://api.zrb.dev/tasks

# v2
curl https://api.zrb.dev/v2/tasks
```

All endpoints in this guide use the prefix: `GET /v2/tasks`, `GET /v2/tasks/{id}`, `POST /v2/tasks`, `PUT /v2/tasks/{id}`, and `DELETE /v2/tasks/{id}`.

## 2. Authentication: Bearer Token

The `X-Auth-Token` header is gone. The `Authorization` header with a Bearer token is required, and any request carrying `X-Auth-Token` is rejected with HTTP 401. Issue a token in the Zrb console — API keys issued for v1 will not work.

```bash
# v1
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.dev/tasks

# v2
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.dev/v2/tasks
```

## 3. Task IDs: Integer → UUID

`id` is now a UUID string instead of an auto-assigned integer. This affects every response, every `{id}` path parameter, and any code that stores, compares, or indexes tasks by numeric id.

```json
// v1
{ "id": 42, "title": "Write tests", "done": false, "created_at": "2024-01-15T10:30:00Z" }

// v2
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z" }
```

Treat ids as opaque strings. There is no mapping from old integer ids to new UUIDs — they are unrelated identifiers — so re-key any local data, caches, or foreign references that assumed `id` was a number.

## 4. Field Rename: `done` → `completed`

The `done` field is renamed to `completed` everywhere: list and get responses, create requests, and update requests. Semantics and the default (`false`) are unchanged, but the v2 update endpoint accepts `completed`, not `done`.

```json
// v1 — GET /tasks response and PUT /tasks/{id} body
{ "id": 1, "title": "Ship v1", "done": true }

// v2 — GET /v2/tasks response and PUT /v2/tasks/{id} body
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Ship v1", "completed": true }
```

Search your codebase for both keys: any serializer, UI binding, or test that reads or writes `done` must switch to `completed`.

## 5. `project_id` Is Required on Create

`POST /v2/tasks` now requires `project_id` in the request body. Omitting it returns HTTP 422, so every create call must include a project. Get the project id from the projects API or the Zrb console.

```json
// v1 — POST /tasks
{ "title": "New task title" }

// v2 — POST /v2/tasks
{ "title": "New task title", "project_id": "proj_abc123" }
```

A create without `project_id` is rejected:

```json
// HTTP 422
{ "title": "New task title" }
```

## 6. List Responses: Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope with `items`, `total`, and `next_cursor`; when `next_cursor` is non-null, pass it back as `?cursor=` to fetch the next page. `limit` caps page size (default 20).

```json
// v1 — GET /tasks
[ { "id": 1, "title": "Buy milk", "done": false, "created_at": "…" },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "…" } ]

// v2 — GET /v2/tasks
{
  "items": [ { "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "…" } ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Iterate until `next_cursor` is null:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.zrb.dev/v2/tasks?cursor=cursor_xyz&limit=20"
```

## Migration Checklist

Work through these in order:

- [ ] Upgrade the CLI client (see the upgrade command below).
- [ ] Issue a Bearer token and remove v1 API keys from configuration and secrets.
- [ ] Replace `X-Auth-Token` with `Authorization: Bearer <token>` in every request.
- [ ] Prefix all endpoint paths with `/v2/`.
- [ ] Stop assuming numeric ids: treat task ids as opaque UUID strings and re-key local storage, caches, and foreign references.
- [ ] Rename `done` to `completed` in every read and write path, including tests.
- [ ] Add `project_id` to all create-task payloads.
- [ ] Adapt list consumers to the `{ items, total, next_cursor }` envelope and follow `next_cursor` until it is null.
- [ ] Run the full test suite against v2 and verify each endpoint against the v2 spec.

## Upgrade

```bash
pip install --upgrade zrb
```
