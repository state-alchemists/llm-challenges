# Zrb Task API — v1 → v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. This guide covers every breaking change, with before/after examples, so you can upgrade your integration with confidence.

---

## Table of Contents

1. [Endpoint Prefix: `/tasks` → `/v2/tasks`](#1-endpoint-prefix-tasks---v2tasks)
2. [Authentication Header: `X-Auth-Token` → `Bearer`](#2-authentication-header-x-auth-token---bearer)
3. [Task ID: Integer → UUID String](#3-task-id-integer--uuid-string)
4. [Field Rename: `done` → `completed`](#4-field-rename-done--completed)
5. [Required Field: `project_id` on Task Creation](#5-required-field-project_id-on-task-creation)
6. [List Response: Bare Array → Paginated Envelope](#6-list-response-bare-array--paginated-envelope)
7. [Step-by-Step Migration Checklist](#step-by-step-migration-checklist)
8. [Upgrade Command](#upgrade-command)

---

## 1. Endpoint Prefix: `/tasks` → `/v2/tasks`

All endpoints are now prefixed with `/v2/`. Requests to the old paths return HTTP 404.

**Before (v1)**

```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2)**

```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

If you construct URLs by concatenating a base URL, update the path segment:

```diff
- const baseUrl = "https://api.zrb.dev/tasks";
+ const baseUrl = "https://api.zrb.dev/v2/tasks";
```

---

## 2. Authentication Header: `X-Auth-Token` → `Bearer`

The header and credential format have both changed. Requests using the old header receive HTTP 401.

**Before (v1)**

```
X-Auth-Token: <your_api_key>
```

**After (v2)**

```
Authorization: Bearer <your_api_token>
```

Update your HTTP client configuration:

```diff
  const response = await fetch(url, {
    headers: {
-     "X-Auth-Token": apiKey,
+     "Authorization": `Bearer ${apiToken}`,
    },
  });
```

You will need a new API token for v2. Existing v1 API keys will not work.

---

## 3. Task ID: Integer → UUID String

Task identifiers are now UUID v4 strings instead of auto-incrementing integers. This affects `id` in every response, the `{id}` path parameter on read/update/delete operations, and any local references you store.

**Before (v1)**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2)**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**What this changes in your code:**

- **Lookup calls** — pass the UUID string instead of an integer:

```diff
- GET /tasks/42
+ GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

- **Local storage** — if you cache task IDs, migrate existing integer IDs to their corresponding UUIDs. There is no deterministic mapping; fetch the full task list from the v2 API to obtain the new IDs.

- **Type assertions** — update any type definitions:

```diff
  interface Task {
-   id: number;
+   id: string;
    title: string;
-   done: boolean;
+   completed: boolean;
+   project_id: string;
    created_at: string;
  }
```

---

## 4. Field Rename: `done` → `completed`

The boolean field indicating task completion has been renamed from `done` to `completed`. The semantics are unchanged.

**Before (v1) — Create / Update**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) — Create / Update**

```json
{
  "title": "Updated title",
  "completed": true
}
```

**Before (v1) — Reading**

```javascript
if (task.done) {
  markComplete(task.id);
}
```

**After (v2) — Reading**

```javascript
if (task.completed) {
  markComplete(task.id);
}
```

Search your codebase for references to `task.done`, `["done"]`, or `.done` in any deserialized task object and rename them to `completed`.

---

## 5. Required Field: `project_id` on Task Creation

Every task must now belong to a project. The `project_id` field is required when creating a task. Omitting it returns HTTP 422 with a validation error.

**Before (v1)**

```json
POST /tasks
{
  "title": "New task title"
}
```

**After (v2)**

```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**How to obtain a `project_id`:**

```bash
# List projects via the new projects endpoint (if one exists)
GET /v2/projects
```

If you do not already have a project, create one first. You can use a default project for backward compatibility if your application doesn't use projects natively.

---

## 6. List Response: Bare Array → Paginated Envelope

List endpoints now return a paginated envelope instead of a bare JSON array. The envelope contains `items`, `total`, and `next_cursor` for cursor-based pagination.

**Before (v1)**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2)**

```json
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "b2c3...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

**Update your list parsing:**

```diff
  const response = await fetch("/v2/tasks");
  const data = await response.json();
- const tasks = data;
+ const tasks = data.items;
+ const total = data.total;
+ const nextCursor = data.next_cursor;
```

**Paginating through results:**

```javascript
function fetchAllTasks() {
  const allTasks = [];
  async function fetchPage(cursor) {
    const url = cursor
      ? `/v2/tasks?cursor=${cursor}&limit=100`
      : `/v2/tasks?limit=100`;
    const res = await fetch(url);
    const page = await res.json();
    allTasks.push(...page.items);
    if (page.next_cursor) {
      await fetchPage(page.next_cursor);
    }
    return allTasks;
  }
  return fetchPage(null);
}
```

The default page size is 20. Use the `limit` query parameter to adjust it.

---

## Step-by-Step Migration Checklist

- [ ] **Issue new API tokens** — Generate v2 Bearer tokens for each environment (dev, staging, production). v1 API keys will not work.
- [ ] **Update authentication headers** — Replace `X-Auth-Token` with `Authorization: Bearer` in every HTTP client configuration and test fixture.
- [ ] **Update endpoint paths** — Prefix all API routes with `/v2/`. Update any hardcoded URL constants in your codebase.
- [ ] **Create projects** — Set up projects via the v2 API (or use the default project) and note their `project_id` values.
- [ ] **Update task creation calls** — Add `project_id` to every `POST /v2/tasks` request body.
- [ ] **Rename `done` to `completed`** — Audit all read and write paths that reference the `done` field on task objects. Update serialization, deserialization, and any conditional logic.
- [ ] **Update ID type** — Change `id` fields from integer to string in your type/interface definitions. Review any code that does arithmetic on task IDs, compares them numerically, or relies on auto-increment ordering.
- [ ] **Update list response parsing** — Replace bare-array parsing with the paginated envelope (`data.items`). Add `total` and `next_cursor` handling if you paginate.
- [ ] **Migrate stored IDs** — If you cache v1 integer task IDs locally, fetch the full task list from v2 to build a mapping of integer → UUID.
- [ ] **Update tests** — Audit integration tests for all of the above. Remember that `GET /v2/tasks/{id}` now expects a UUID in the path.
- [ ] **Deploy and monitor** — Roll out to a staging environment first. Watch for HTTP 401, 404, and 422 responses in your logs — each pinpoints a specific migration gap.

---

## Upgrade Command

```bash
# Install or upgrade to Zrb CLI v2
pip install --upgrade zrb

# Verify the installed version
zrb --version
# Expected: zrb 2.x.x
```

After upgrading, run your test suite. Any integration tests hitting the task API will surface remaining migration gaps.

---

*Need help? Open an issue at https://github.com/state-alchemists/zrb/issues*
