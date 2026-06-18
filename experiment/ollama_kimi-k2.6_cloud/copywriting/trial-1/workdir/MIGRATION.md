# Migrating from Zrb CLI v1 to v2

This guide covers every breaking change in Zrb CLI v2 and how to update your integrations. If you are currently on v1, follow the sections below in order.

---

## Overview of Breaking Changes

v2 introduces projects, cursor-based pagination, and stricter authentication. The following six changes are **breaking** and require updates to any client code:

1. Base URL prefix moved to `/v2/`
2. Authentication header switched from `X-Auth-Token` to `Authorization: Bearer`
3. Task `id` type changed from integer to UUID string
4. Task field `done` renamed to `completed`
5. Task creation now requires `project_id`
6. List endpoints return a paginated envelope instead of a bare array

---

## 1. Base URL Prefix

All endpoints are now scoped under `/v2/`. Requests to the old root paths will return `404`.

### Before (v1)
```http
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

### After (v2)
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Action:** Update every hard-coded route or base URL in your HTTP clients, SDK wrappers, and Postman collections.

---

## 2. Authentication Header

v1 accepted a custom `X-Auth-Token` header. v2 enforces RFC 6750 Bearer tokens.

### Before (v1)
```http
X-Auth-Token: <your_api_key>
```

### After (v2)
```http
Authorization: Bearer <your_api_token>
```

**Action:** Replace `X-Auth-Token` with `Authorization: Bearer` in every request builder. Requests sent with the old header will receive `401 Unauthorized`.

---

## 3. Task ID Type Changed to UUID

Task identifiers are no longer integers; they are UUID strings. This affects deserialization logic and any database columns or URL parameters that assumed an integer.

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

**Action:** Update typed models, ORM mappings, and URL path segments to treat `id` as a `string` (UUID) instead of an `integer`.

---

## 4. Field Rename: `done` → `completed`

The boolean flag indicating task status has been renamed. Sending `done` in request bodies will be ignored or rejected, depending on the endpoint.

### Before (v1)
```json
{
  "title": "Updated title",
  "done": true
}
```

### After (v2)
```json
{
  "title": "Updated title",
  "completed": true
}
```

**Action:** Search your codebase for `"done"` in task-related payloads and rename the key to `"completed"`.

---

## 5. Task Creation Requires `project_id`

Creating a task now requires associating it with a project. Omitting `project_id` returns `422 Unprocessable Entity`.

### Before (v1)
```json
{
  "title": "New task title"
}
```

### After (v2)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Action:** Ensure your create-task forms and automated scripts capture or hard-code a valid `project_id`.

---

## 6. Paginated List Responses

`GET /v2/tasks` no longer returns a bare JSON array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`. You must traverse pages using the `cursor` query parameter.

### Before (v1)
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2)
```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3d4e5-f6a7-8901-bcde-f12345678901", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Action:** Rewrite list consumers to extract tasks from the `items` key. If you fetch more than one page, loop using `?cursor=<value>` until `next_cursor` is absent.

---

## Migration Checklist

Use this checklist to roll out the upgrade safely:

- [ ] **Upgrade the CLI** to v2 (see command below).
- [ ] **Rotate credentials** if your old key was tied to v1-specific scopes.
- [ ] **Update base URLs** in all clients, SDK configs, and environment variables (`/tasks` → `/v2/tasks`).
- [ ] **Replace auth headers** (`X-Auth-Token` → `Authorization: Bearer`).
- [ ] **Migrate data models** so that `id` fields are strings (UUID) instead of integers.
- [ ] **Rename `done` to `completed`** in all request/response payloads.
- [ ] **Add `project_id`** to every task creation flow and seed existing projects.
- [ ] **Rewrite list consumers** to read `response.items` and support cursor pagination.
- [ ] **Run integration tests** against a v2 staging endpoint before switching production traffic.
- [ ] **Update documentation and runbooks** that reference v1 URLs or field names.

---

## Upgrade Command

Install or upgrade to v2 via your package manager:

```bash
npm install -g @zrb/cli@latest
```

(If you use a different installation method—Homebrew, Docker, or a manual binary—replace the command above with the equivalent `update` or `pull` for v2.)

---

*Need help? Open an issue in the [Zrb CLI repository](https://github.com/state-alchemists/zrb) with the label `migration/v2`.*
