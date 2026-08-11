# Zrb CLI v1 → v2 Migration Guide

This guide helps you migrate your integrations from Zrb CLI v1 to v2. It assumes you are already familiar with the v1 Task API and want to update your scripts, clients, and automation to the new v2 surface.

**What changed at a glance:**

- All endpoints are now prefixed with `/v2/`.
- Authentication uses a Bearer token header.
- Task IDs are UUID strings instead of integers.
- The `done` field is renamed to `completed`.
- Creating a task now requires a `project_id`.
- List endpoints return a paginated envelope instead of a bare array.

---

## 1. API Version Prefix

**Breaking change:** All task endpoints are now version-prefixed.

### Before (v1)
```bash
curl -X GET https://api.example.com/tasks
curl -X GET https://api.example.com/tasks/42
curl -X POST https://api.example.com/tasks
curl -X PUT https://api.example.com/tasks/42
curl -X DELETE https://api.example.com/tasks/42
```

### After (v2)
```bash
curl -X GET https://api.example.com/v2/tasks
curl -X GET https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X POST https://api.example.com/v2/tasks
curl -X PUT https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication Header

**Breaking change:** The `X-Auth-Token` header is removed. Requests using it will receive HTTP 401.

### Before (v1)
```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.example.com/tasks
```

### After (v2)
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.example.com/v2/tasks
```

> **Action required:** Update every client and script that sets `X-Auth-Token` to use the `Authorization: Bearer` scheme instead. Verify that your API token is still valid under v2.

---

## 3. Task ID Type Changed to UUID

**Breaking change:** Task IDs are no longer integers. They are UUID strings.

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

> **Action required:** Update any storage, URL construction, or deserialization logic that assumes `id` is an integer. Treat `id` as an opaque string everywhere.

---

## 4. Field Rename: `done` → `completed`

**Breaking change:** The task status field `done` is renamed to `completed`.

### Before (v1)
```bash
curl -X PUT https://api.example.com/tasks/42 \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "Updated title", "done": true}'
```

```json
{
  "id": 42,
  "title": "Updated title",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2)
```bash
curl -X PUT https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{"title": "Updated title", "completed": true}'
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

> **Action required:** Rename every reference from `done` to `completed` in request payloads, response parsing, and conditional logic.

---

## 5. Required `project_id` on Task Creation

**Breaking change:** Creating a task now requires a `project_id`. Omitting it returns HTTP 422.

### Before (v1)
```bash
curl -X POST https://api.example.com/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

### After (v2)
```bash
curl -X POST https://api.example.com/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

> **Action required:** Identify the correct `project_id` for each task you create and include it in every `POST /v2/tasks` request. If you have existing v1 tasks that need to be grouped, decide on a project mapping before migrating data.

---

## 6. Paginated List Responses

**Breaking change:** `GET /tasks` no longer returns a bare array. It returns a paginated envelope.

### Before (v1)
```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.example.com/tasks
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
  "https://api.example.com/v2/tasks?limit=20"
```

**Response:**
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "..."
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Fetching the next page:**
```bash
curl -H "Authorization: Bearer <your_api_token>" \
  "https://api.example.com/v2/tasks?limit=20&cursor=cursor_xyz"
```

> **Action required:** Update any list-consumer logic to read from the `items` key. Implement cursor-based pagination if you iterate over large result sets.

---

## Migration Checklist

Use this checklist to ensure your upgrade is complete:

- [ ] **Upgrade the CLI** to v2 (see command below).
- [ ] **Audit all API URLs.** Replace every bare `/tasks` path with `/v2/tasks`.
- [ ] **Rotate authentication headers.** Replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Update ID handling.** Ensure task IDs are stored and passed as strings, not integers.
- [ ] **Rename status field.** Replace every occurrence of `done` with `completed` in payloads and parsers.
- [ ] **Add `project_id` to task creation.** Verify every `POST` to `/v2/tasks` includes a valid `project_id`.
- [ ] **Adapt list consumers.** Update code that parses list responses to expect the paginated envelope (`items`, `total`, `next_cursor`).
- [ ] **Test integrations.** Run your test suite against the v2 endpoints in a non-production environment before going live.
- [ ] **Update documentation.** Refresh any internal docs, runbooks, or client libraries that reference the v1 API.

---

## Upgrade Command

Install v2 with:

```bash
pip install --upgrade "zrb>=2.0.0"
```
