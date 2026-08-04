# Zrb API v2 Migration Guide

Zrb API v2 introduces projects, cursor-based pagination, and stricter authentication. It also renames one field and changes the task ID type, so every client built against v1 needs changes before it will work against v2.

This guide is for developers already shipping on v1. Each breaking change below shows the v1 behavior, the v2 replacement, and what you have to do. The full v1 and v2 references are in `v1_spec.md` and `v2_spec.md`; this guide covers only what differs.

## Breaking Changes at a Glance

| Area | v1 | v2 |
|---|---|---|
| Endpoint prefix | `/tasks` | `/v2/tasks` |
| Auth header | `X-Auth-Token` | `Authorization: Bearer` |
| Task ID | integer | UUID string |
| Completion flag | `done` | `completed` |
| Create task | title only | `title` + required `project_id` |
| List response | bare array | paginated envelope |

## 1. Endpoint Paths Are Prefixed with `/v2/`

Every endpoint moved under the `/v2/` prefix. All five routes — list, get, create, update, delete — are affected, so a path update is the first thing to do in every client.

Before:

```
GET /tasks
POST /tasks
PUT /tasks/{id}
```

After:

```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
```

## 2. Auth Header Replaced by Bearer Token

The `X-Auth-Token` header no longer works. Requests that still send it receive HTTP 401, so update your auth layer before you flip traffic to v2. The new header is `Authorization: Bearer`.

Before:

```
X-Auth-Token: <your_api_key>
```

After:

```
Authorization: Bearer <your_api_token>
```

## 3. Task IDs Are Now UUID Strings

`id` was an auto-assigned integer in v1. In v2 it is a UUID string such as `a1b2c3d4-e5f6-7890-abcd-ef1234567890`. This ripples into URL paths (`GET /v2/tasks/{id}`), response parsing, and any stored references you keep.

Before:

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

After:

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

If you persist task IDs in your own database, plan a remap from integers to UUIDs, and make sure code that parsed `id` as a number is updated.

## 4. `done` Is Renamed to `completed`

The boolean flag marking a task finished is now `completed`. The rename applies in both directions: v2 responses contain `completed`, and updates must send `completed` — `done` is no longer accepted.

Before:

```json
{
  "done": true
}
```

After:

```json
{
  "completed": true
}
```

Update request builders and response deserializers together, or your `PUT` payloads and your JSON parsing will silently disagree.

## 5. Creating a Task Now Requires `project_id`

v2 introduces projects, and every task belongs to one. `POST /v2/tasks` now requires `project_id` in the request body; omitting it returns HTTP 422. You need to create a project first and pass its ID on every task creation.

Before:

```
POST /tasks
{
  "title": "New task title"
}
```

After:

```
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

A successful create still returns HTTP 201 with the created task object.

## 6. List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns an envelope containing `items`, `total`, and `next_cursor`. Page through results by passing `?cursor=<next_cursor>`; `limit` (default 20) controls page size. A missing `next_cursor` means you are on the last page.

Before:

```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." }
]
```

After:

```json
{
  "items": [
    { "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Clients that assumed `response` was a list must now read `response.items` and loop on `next_cursor` instead of assuming one request returns everything.

## What Did Not Change

- `title` and `created_at` keep their v1 meaning and format.
- Create still returns HTTP 201; delete still returns HTTP 204.
- Update semantics are unchanged: `PUT /v2/tasks/{id}` with all fields optional.

## Migration Checklist

Work through these in order:

- [ ] Update all endpoint URLs to the `/v2/` prefix.
- [ ] Replace `X-Auth-Token` with `Authorization: Bearer <token>` in every client and test script.
- [ ] Migrate stored task IDs from integers to UUIDs and update URL construction and parsing.
- [ ] Rename `done` to `completed` in request bodies and response deserializers.
- [ ] Create projects in v2 and pass `project_id` on every task creation.
- [ ] Update list handling to read `items` from the envelope and follow `next_cursor` until the last page.
- [ ] Run your full test suite against v2; confirm no HTTP 401 (auth) or 422 (`project_id`) responses.
- [ ] After the cutover window, delete v1-only code paths.

## Upgrade

```bash
pip install --upgrade zrb
```
