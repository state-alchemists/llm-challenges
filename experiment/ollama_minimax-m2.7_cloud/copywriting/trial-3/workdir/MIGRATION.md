# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change when upgrading from Zrb Task API v1 to v2. Each section shows the v1 pattern, the v2 replacement, and what you need to do.

**Estimated migration time:** 30–60 minutes depending on codebase size.

---

## Table of Contents

1. [Authentication Header](#1-authentication-header)
2. [API Endpoint Prefix](#2-api-endpoint-prefix)
3. [Task ID Type](#3-task-id-type)
4. [Task Field Rename: `done` → `completed`](#4-task-field-rename-done--completed)
5. [Task Creation Requires `project_id`](#5-task-creation-requires-project_id)
6. [List Response Envelope](#6-list-response-envelope)
7. [Migration Checklist](#migration-checklist)
8. [Upgrade Command](#upgrade-command)

---

## 1. Authentication Header

**What changed:** The authentication header has been replaced entirely.

| Version | Header |
|---------|--------|
| v1 | `X-Auth-Token: <your_api_key>` |
| v2 | `Authorization: Bearer <your_api_token>` |

Requests sent with `X-Auth-Token` will receive **HTTP 401 Unauthorized** in v2.

### Before (v1)

```http
GET /tasks HTTP/1.1
Host: api.zrb.io
X-Auth-Token: sk_live_abc123
```

### After (v2)

```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.io
Authorization: Bearer sk_live_abc123
```

### Action required

Search your codebase for `X-Auth-Token` and replace it with `Authorization: Bearer`.

---

## 2. API Endpoint Prefix

**What changed:** All endpoints are now versioned under `/v2/`.

| Operation | v1 Endpoint | v2 Endpoint |
|-----------|-------------|-------------|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

### Before (v1)

```javascript
const response = await fetch('/tasks');
const tasks = await response.json();
```

### After (v2)

```javascript
const response = await fetch('/v2/tasks');
const { items: tasks } = await response.json();
```

### Action required

Add `/v2` prefix to every API endpoint in your integration.

---

## 3. Task ID Type

**What changed:** Task `id` is now a UUID string instead of an integer.

| Version | Type | Example |
|---------|------|---------|
| v1 | integer | `42` |
| v2 | UUID string | `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"` |

This affects how you reference tasks in URLs, store them in databases, and compare equality.

### Before (v1)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

### After (v2)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

### Action required

- Update any database columns or localStorage keys that hold task IDs from `integer` to `string`.
- Update URL path parameter types from number to string.
- Update any ID comparison logic (e.g., `taskId === 42` → `taskId === "a1b2c3d4-..."`).

---

## 4. Task Field Rename: `done` → `completed`

**What changed:** The boolean status field has been renamed.

| Version | Field | Type |
|---------|-------|------|
| v1 | `done` | boolean |
| v2 | `completed` | boolean |

### Before (v1)

```json
{
  "id": 1,
  "title": "Ship v1",
  "done": true
}
```

### After (v2)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Ship v1",
  "completed": true,
  "project_id": "proj_abc123"
}
```

### Action required

Search for `.done` and `done:` in JSON payloads and conditionals. Rename to `.completed` and `completed:`.

---

## 5. Task Creation Requires `project_id`

**What changed:** Creating a task now requires a `project_id`. Tasks cannot exist without a project.

| Version | Required fields for `POST /tasks` |
|---------|-------------------------------------|
| v1 | `title` only |
| v2 | `title` **and** `project_id` |

Omitting `project_id` returns **HTTP 422 Unprocessable Entity**.

### Before (v1)

```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "Write migration guide"
}
```

### After (v2)

```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "Write migration guide",
  "project_id": "proj_abc123"
}
```

### Action required

- Identify which project new tasks should belong to. You may need to create a project first via `POST /v2/projects`.
- Add `project_id` to every task creation call.
- If your v1 integration allowed "unassigned" tasks, decide which project they now belong to.

---

## 6. List Response Envelope

**What changed:** List endpoints no longer return a bare array. They return a paginated envelope.

| Version | Response shape |
|---------|----------------|
| v1 | `[{ task }, { task }]` |
| v2 | `{ "items": [...], "total": 42, "next_cursor": "cursor_xyz" }` |

Pagination is cursor-based. To fetch the next page, pass `?cursor=<next_cursor>`.

### Before (v1)

```javascript
const tasks = await fetch('/tasks').then(r => r.json());
// tasks is an array: [{ id: 1, ... }, { id: 2, ... }]
tasks.forEach(task => render(task));
```

### After (v2)

```javascript
const { items: tasks, total, next_cursor } = await fetch('/v2/tasks').then(r => r.json());
// tasks is an array inside an envelope
tasks.forEach(task => render(task));

// Pagination: fetch next page
if (next_cursor) {
  const next = await fetch(`/v2/tasks?cursor=${next_cursor}`).then(r => r.json());
  // ...
}
```

### Action required

- Update list response handling to destructure `items` from the envelope.
- If you rely on `array.length` for total count, use `total` instead.
- Add cursor-based pagination loop if you need to fetch all pages.

---

## Migration Checklist

Run through each item. Mark `[x]` as you complete it.

- [ ] Replace all `X-Auth-Token` headers with `Authorization: Bearer <token>`
- [ ] Add `/v2` prefix to every API endpoint URL
- [ ] Update task ID storage type from integer to string (UUID)
- [ ] Update URL path parameters for task IDs from number to string
- [ ] Rename all `done` fields to `completed` in JSON payloads and conditionals
- [ ] Add `project_id` to every task creation payload (required field)
- [ ] Update list response handling to extract `items` from envelope
- [ ] Update total count references from `array.length` to `total` field
- [ ] Add pagination loop using `next_cursor` if fetching all pages
- [ ] Run your integration tests against the v2 endpoint
- [ ] Update any documentation or internal runbooks with new endpoint paths

---

## Upgrade Command

Once you have completed the checklist, update your package or CLI dependency:

```bash
# npm
npm install zrb-cli@latest

# yarn
yarn upgrade zrb-cli@latest

# pip
pip install --upgrade zrb-cli
```

After upgrading, verify your configuration:

```bash
zrb config show
```

Check that the displayed API endpoint starts with `/v2/` and that your auth token is configured for Bearer authentication.

---

If you run into issues, the full v2 specification is at `v2_spec.md`. For community support, open an issue at `https://github.com/zrb/zrb-cli/issues`.
