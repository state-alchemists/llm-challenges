# Zrb CLI v1 → v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, stricter authentication, and several breaking API changes. This guide covers every change you need to make to move from v1 to v2.

For the full v2 API reference, see [`v2_spec.md`](./v2_spec.md).

---

## 1. Base URL Prefix — `/tasks` → `/v2/tasks`

All endpoints are now served under `/v2/`. Requests to the old paths will fail.

**Before (v1):**

```http
GET /tasks
POST /tasks
GET /tasks/42
PUT /tasks/42
DELETE /tasks/42
```

**After (v2):**

```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

## 2. Authentication — `X-Auth-Token` → Bearer Token

The `X-Auth-Token` header is removed. All requests must use a Bearer token in the `Authorization` header. Requests with the old header receive HTTP 401.

**Before (v1):**

```http
X-Auth-Token: your_api_key
```

**After (v2):**

```http
Authorization: Bearer your_api_token
```

Update your client's auth configuration accordingly. If you are generating tokens from API keys, run the migration command (see below) to obtain a v2 token.

---

## 3. Task ID Type — Integer → UUID String

Task identifiers changed from auto-incrementing integers to UUID strings. All endpoints that reference task IDs now expect UUIDs.

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

**Impact:**

- Local ID references (cached IDs, foreign-key mappings) must be migrated. Run the `zrb migrate ids` command to produce a mapping of old integer IDs to new UUIDs.
- Client code that parses `id` as an integer will need a type change. UUID validation and formatting utilities are available in Zrb's SDK packages.

---

## 4. Field Rename — `done` → `completed`

The `done` boolean field is renamed to `completed` in both request and response payloads.

**Before (v1) — request body:**

```json
{
  "title": "Write tests",
  "done": true
}
```

**After (v2) — request body:**

```json
{
  "title": "Write tests",
  "completed": true
}
```

**Before (v1) — response body:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — response body:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Impact:**

- All client code referencing `task.done` or `task["done"]` must be updated to `task.completed` / `task["completed"]`.
- The v2 API will silently ignore the `done` field — your request will appear to succeed but the field will not be applied.

---

## 5. New Required Field — `project_id`

Task creation now requires a `project_id` string in the request body. Omitting it returns HTTP 422.

**Before (v1):**

```http
POST /tasks
Content-Type: application/json

{
  "title": "New task"
}
```

**After (v2):**

```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task",
  "project_id": "proj_abc123"
}
```

**Impact:**

- You must create or identify a project before creating tasks. Use `GET /v2/projects` to list available projects, or create one via `POST /v2/projects`.
- All callers that create tasks must be updated to supply `project_id`.

---

## 6. List Response Format — Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return a paginated envelope with `items`, `total`, and `next_cursor`. Bare array responses are not supported.

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
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6a7b8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Impact:**

- Client code that iterates the response as a top-level array must now access `response.items`.
- The default page size is 20. Use `?limit=<N>` to adjust and `?cursor=<next_cursor>` to fetch subsequent pages.
- When `next_cursor` is `null`, no further pages exist.

---

## Migration Checklist

Use this checklist to track your migration progress.

- [ ] **Update base URLs** — Replace `/tasks` with `/v2/tasks` in all API calls.
- [ ] **Switch auth header** — Replace `X-Auth-Token` with `Authorization: Bearer <token>`.
- [ ] **Generate v2 tokens** — Run `zrb migrate tokens` to convert existing API keys to v2 Bearer tokens.
- [ ] **Migrate ID references** — Run `zrb migrate ids` to obtain the integer-to-UUID mapping. Update all ID caches, foreign-key stores, and hardcoded references.
- [ ] **Update `done` → `completed`** — Search and replace all `done` field references in request bodies, response parsers, and client models.
- [ ] **Supply `project_id`** — Create projects as needed and update all task creation calls to include `project_id`.
- [ ] **Update list response parsing** — Change array iteration to `response.items`. Add cursor-based pagination logic using `next_cursor`.
- [ ] **Update Client SDK** — If using a Zrb client library, upgrade to the v2-compatible version.
- [ ] **Run integration tests** — Validate auth, CRUD, pagination, and error handling against the v2 endpoints.

---

## Upgrade Command

When you're ready to switch, run:

```bash
zrb upgrade --to v2
```

This command runs the token and ID migrations, updates your local configuration files, and prints a summary of migrated resources.
