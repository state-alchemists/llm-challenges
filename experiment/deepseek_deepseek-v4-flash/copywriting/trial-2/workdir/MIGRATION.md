# Zrb Task API: Migrating from v1 to v2

Zrb CLI v2 introduces projects, stricter authentication, and cursor-based pagination. Every v1 integration will break in at least one of the six ways below, so treat this as a hard cutover, not a drop-in upgrade. This guide walks through each breaking change with before/after examples, then closes with a step-by-step checklist. If you are already on v1, read sections 1–6 in order — later changes build on earlier ones.

## Breaking Changes at a Glance

1. All endpoints move under the `/v2/` prefix.
2. The `X-Auth-Token` header is replaced by `Authorization: Bearer <token>`; requests with the old header get HTTP 401.
3. Task `id` changes from an integer to a UUID string.
4. Task field `done` is renamed to `completed`.
5. Task creation now requires `project_id`; omitting it returns HTTP 422.
6. List endpoints return a paginated envelope instead of a bare array.

## 1. Endpoint Prefix: Everything Moves Under `/v2/`

Every endpoint is now served under `/v2/`. Old paths are not routed to the new API, so update the base paths in clients, SDKs, and documentation in the same change that updates the auth header — otherwise you will be debugging 401s and 404s at the same time.

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

## 2. Authentication: Bearer Tokens Replace `X-Auth-Token`

v2 drops the `X-Auth-Token` header in favor of a standard Bearer token. Requests that still send `X-Auth-Token` receive HTTP 401, so rotate credentials and update every client, cron job, and CI job in one pass — a v1 API key will not authenticate against v2.

**Before (v1):**
```text
X-Auth-Token: <your_api_key>
```

**After (v2):**
```text
Authorization: Bearer <your_api_token>
```

## 3. Task IDs: Integers Become UUID Strings

Task `id` is now a UUID string instead of an auto-assigned integer. This changes how you address tasks in paths — `GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890` — and breaks any client code that treats the id as a number: arithmetic, array indexing, or integer type checks. Store and pass ids as opaque strings.

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

## 4. `done` Is Renamed to `completed`

The task completion flag is now `completed`. This touches every request and response that reads or writes the flag: read `completed` in responses and send `completed` in update bodies. The v1 `done` name is gone from the schema, so update request bodies and response readers together.

**Before (v1):**
```text
PUT /tasks/42
{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**
```text
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{
  "title": "Updated title",
  "completed": true
}
```

## 5. `project_id` Is Required on Create

Task creation now requires `project_id`, and every task object carries it. `POST /v2/tasks` without `project_id` returns HTTP 422. Decide which project new tasks belong to and thread the id through your creation code — it is not optional and cannot default to `null`.

**Before (v1):**
```text
POST /tasks
{
  "title": "New task title"
}
```

**After (v2):**
```text
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

## 6. List Endpoints Return a Paginated Envelope

List responses are no longer bare arrays. Every list endpoint returns an envelope:

```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Read results from `items`, not from the response root. Each page is capped at `limit` (default 20), and you fetch the next page by passing `?cursor=<next_cursor>`; keep following `next_cursor` until the envelope stops including one. Clients that assumed "the array is everything" must now loop over pages.

**Before (v1):**
```text
GET /tasks
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**
```text
GET /v2/tasks
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Next page (v2):**
```text
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

## What Has Not Changed

`title` and `created_at` keep their meaning and format, `DELETE /v2/tasks/{id}` still returns HTTP 204, and create still returns the created task with HTTP 201. Update the shape, not the semantics.

## Step-by-Step Migration Checklist

1. Upgrade the CLI to v2 with `pip install -U zrb`.
2. Issue v2 tokens and replace every `X-Auth-Token` header with `Authorization: Bearer <token>`; remove v1 keys from configs, cron jobs, and CI.
3. Prefix all endpoint paths with `/v2/` in clients, SDKs, and docs.
4. Treat task ids as opaque UUID strings: stop parsing them as integers and update path construction.
5. Rename `done` to `completed` in request bodies and response handling.
6. Add `project_id` to every create call and handle HTTP 422 for missing values.
7. Replace bare-array list parsing with the paginated envelope: read `items`, loop on `next_cursor`, and honor `limit`.
8. Run the full integration test suite against a v2 staging environment before switching production traffic.

## Upgrade

Install or upgrade to v2:

```bash
pip install -U zrb
```
