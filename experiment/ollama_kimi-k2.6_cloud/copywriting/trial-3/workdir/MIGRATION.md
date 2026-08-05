# Zrb Task API v1 → v2 Migration Guide

This guide covers every breaking change in Zrb Task API v2 and how to migrate your existing v1 integrations. If your code already calls the v1 endpoints, work through each section below and update the corresponding requests, headers, and response handling.

---

## Breaking Change 1: API Version Prefix

All endpoints are now prefixed with `/v2/`.

**v1 (before):**

```bash
curl https://api.zrb.example/tasks
curl https://api.zrb.example/tasks/42
curl -X POST https://api.zrb.example/tasks
curl -X PUT https://api.zrb.example/tasks/42
curl -X DELETE https://api.zrb.example/tasks/42
```

**v2 (after):**

```bash
curl https://api.zrb.example/v2/tasks
curl https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X POST https://api.zrb.example/v2/tasks
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## Breaking Change 2: Authentication Header

The `X-Auth-Token` header is no longer accepted. v2 uses a standard Bearer token in the `Authorization` header. Requests sent with `X-Auth-Token` will receive HTTP 401.

**v1 (before):**

```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.example/tasks
```

**v2 (after):**

```bash
curl -H "Authorization: Bearer <your_api_token>" https://api.zrb.example/v2/tasks
```

---

## Breaking Change 3: Task `id` Type Changed from Integer to UUID

Task identifiers are now UUID strings instead of integers. Update any code that assumes `id` is an integer or that performs numeric comparison/ordering on IDs.

**v1 (before):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**v2 (after):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

## Breaking Change 4: Task Field `done` Renamed to `completed`

The boolean field that tracks whether a task is finished has been renamed from `done` to `completed`. Sending `done` in a request body will be ignored or rejected.

**v1 (before):**

```bash
curl -X PUT https://api.zrb.example/tasks/42 \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated title", "done": true}'
```

**v2 (after):**

```bash
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Updated title", "completed": true}'
```

---

## Breaking Change 5: Task Creation Requires `project_id`

Creating a task now requires a `project_id` field in the request body. Omitting it returns HTTP 422.

**v1 (before):**

```bash
curl -X POST https://api.zrb.example/tasks \
  -H "X-Auth-Token: <your_api_key>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**v2 (after):**

```bash
curl -X POST https://api.zrb.example/v2/tasks \
  -H "Authorization: Bearer <your_api_token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

---

## Breaking Change 6: List Endpoints Return a Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. It now returns a paginated envelope containing `items`, `total`, and `next_cursor`. You must update any code that iterates over the top-level array or expects an immediate list of objects.

**v1 (before):**

```bash
curl -H "X-Auth-Token: <your_api_key>" https://api.zrb.example/tasks
```

Response:

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**v2 (after):**

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.example/v2/tasks?limit=20"
```

Response:

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To fetch the next page, pass the cursor:

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.zrb.example/v2/tasks?limit=20&cursor=cursor_xyz"
```

---

## Step-by-Step Migration Checklist

Use this checklist to verify every integration point is updated before you deploy to production.

- [ ] **Base URL / Prefix**: Update all hardcoded endpoint paths to include `/v2/`.
- [ ] **Authentication**: Replace the `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] **Task ID type**: Change task ID variables and database columns from integer to string (UUID).
- [ ] **Field rename**: Replace every reference to `done` with `completed` in request bodies, response parsing, and UI bindings.
- [ ] **Task creation**: Add `project_id` to all task creation payloads; handle HTTP 422 when it is missing.
- [ ] **List pagination**: Update list-task consumers to read `response.items` instead of the top-level array; implement cursor pagination if you fetch more than one page.
- [ ] **Error handling**: Review for new HTTP 401 (auth) and HTTP 422 (missing `project_id`) responses.
- [ ] **Tests / mocks**: Update unit and integration tests that mock Zrb responses to use v2 shapes (UUID IDs, paginated envelopes, `completed`).
- [ ] **Staging validation**: Run the full test suite against the v2 staging environment before switching production traffic.

---

## Upgrade Command

Install or upgrade to the latest v2 CLI:

```bash
pip install --upgrade zrb>=2.0.0
```

After upgrading, run `zrb --version` to confirm you are on v2, then proceed through the checklist above.
