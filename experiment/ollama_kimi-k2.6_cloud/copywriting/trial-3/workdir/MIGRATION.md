# Zrb CLI v1 to v2 Migration Guide

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Review each section, update your code, and run through the checklist at the end before deploying to production.

---

## 1. Endpoint Prefix

All API endpoints are now version-prefixed with `/v2/`.

### Before (v1)
```bash
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

### After (v2)
```bash
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

> **Action required:** Update every hardcoded path or base URL builder in your codebase.

---

## 2. Authentication Header

The authentication header has changed from `X-Auth-Token` to a Bearer token in the `Authorization` header.

### Before (v1)
```bash
curl -H "X-Auth-Token: <your_api_key>" \
     https://api.zrb.example/tasks
```

### After (v2)
```bash
curl -H "Authorization: Bearer <your_api_token>" \
     https://api.zrb.example/v2/tasks
```

> **Action required:** Update request headers. Requests using `X-Auth-Token` will receive HTTP 401.

---

## 3. Task `id` Changed from Integer to UUID

Task identifiers are now UUID strings instead of auto-incrementing integers.

### Before (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

> **Action required:**
> - Replace any integer parsing or arithmetic on `id`.
> - Update URL builders that concatenate integer IDs into paths.
> - Update database columns or local caches that store task IDs.

---

## 4. Task Field `done` Renamed to `completed`

The boolean flag marking a task as finished is now called `completed`.

### Before (v1)
```bash
curl -X PUT https://api.zrb.example/tasks/42 \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

```json
{
  "id": 42,
  "title": "Ship v1",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2)
```bash
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"completed": true}'
```

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Ship v1",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

> **Action required:** Rename every occurrence of `done` to `completed` in request bodies, response parsing, and conditional logic.

---

## 5. Task Creation Now Requires `project_id`

Creating a task without a `project_id` is no longer allowed and will return HTTP 422.

### Before (v1)
```bash
curl -X POST https://api.zrb.example/tasks \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

### After (v2)
```bash
curl -X POST https://api.zrb.example/v2/tasks \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

> **Action required:**
> - Ensure your application knows the target `project_id` before creating tasks.
> - Update all `POST /v2/tasks` call sites to include `project_id` in the request body.
> - Add server-side or client-side validation so users cannot submit without it.

---

## 6. List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`.

### Before (v1)
```bash
curl -H "X-Auth-Token: <your_api_key>" \
     https://api.zrb.example/tasks
```

**Response:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)
```bash
curl -H "Authorization: Bearer <your_api_token>" \
     "https://api.zrb.example/v2/tasks?limit=20"
```

**Response:**
```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page:
```bash
curl -H "Authorization: Bearer <your_api_token>" \
     "https://api.zrb.example/v2/tasks?limit=20&cursor=cursor_xyz"
```

> **Action required:**
> - Change response parsing from a top-level array to `response.items`.
> - Implement cursor-based pagination if your UI supports infinite scroll or paginated tables.
> - Use `?limit=<number>` to control page size (default is 20).

---

## Migration Checklist

Use this checklist to verify your upgrade before going live.

- [ ] Update base URL or path construction to prepend `/v2/` to all endpoints.
- [ ] Replace `X-Auth-Token: <key>` with `Authorization: Bearer <token>`.
- [ ] Verify your API token works with the new Bearer format.
- [ ] Change task `id` handling from integers to UUID strings.
- [ ] Rename every `done` field to `completed` in request bodies and response parsers.
- [ ] Add `project_id` to all task creation (`POST`) requests.
- [ ] Update list-task consumers to read `response.items` instead of the raw array.
- [ ] Add pagination support (cursor + limit) for list endpoints if your UI needs it.
- [ ] Run integration tests against the v2 endpoints.
- [ ] Update internal documentation and API client libraries.

---

## Upgrade Command

Install the latest v2 CLI:

```bash
pip install --upgrade zrb>=2.0.0
```

Verify the installed version:

```bash
zrb --version
```

Once the CLI is updated and your code changes are deployed, you are running on v2.
