# Zrb Task API: v1 → v2 Migration Guide

This guide covers every breaking change between the v1 and v2 Zrb Task API.
If you are already using v1, follow each section below to update your
integration. The complete v2 reference is available in `v2_spec.md`.

---

## Breaking Changes

Six breaking changes ship in v2. Each is listed below with its impact,
a before/after example, and the migration step required.

---

### 1. Endpoint URL Prefix

**Change:** All endpoints are now prefixed with `/v2/`.

| v1 | v2 |
|----|----|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

```diff
- curl https://api.zrb.dev/tasks
+ curl https://api.zrb.dev/v2/tasks
```

**Migration:** Prepend `/v2` to every API endpoint path in your client.

---

### 2. Authentication Header

**Change:** The request header changed from `X-Auth-Token` to a standard
Bearer token via `Authorization`. Requests using the old header receive
HTTP 401.

```diff
- X-Auth-Token: <your_api_key>
+ Authorization: Bearer <your_api_token>
```

**Migration:**

1. Generate or obtain a Bearer token from the Zrb console (replaces your
   v1 API key).
2. Replace the `X-Auth-Token` header with `Authorization: Bearer <token>`
   in every request.

> **Note:** Your v1 API key will not work with v2. You must provision a
> new token even if your existing key is still active.

---

### 3. Task `id` Type: Integer → UUID String

**Change:** Task identifiers are now UUID strings instead of auto-incrementing
integers. This affects all endpoints that reference a task by ID (`GET`,
`PUT`, `DELETE`) and all stored references to task IDs in your application.

```diff
  // v1 — integer id
  {
-   "id": 42,
    "title": "Write tests",
    "done": false
  }

  // v2 — UUID string id
  {
+   "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "title": "Write tests",
    "completed": false
  }
```

**Migration:**

- Update any database columns or in-memory data structures that store
  task `id` to accept UUID strings instead of integers.
- Update URL construction in API calls to pass UUIDs (v2 returns 404
  for integer IDs).
- If you expose task IDs in URLs or UI, expect the format to change
  from sequential numbers to UUIDs.

---

### 4. Field Rename: `done` → `completed`

**Change:** The boolean task field `done` is renamed to `completed`.
The old field is absent from v2 responses, and sending `done` in a
request body is silently ignored (the value is not read).

```diff
  // v1
  {
    "id": 1,
    "title": "Ship v1",
-   "done": true
  }

  // v2
  {
    "id": "a1b2c3d4-...",
    "title": "Ship v1",
+   "completed": true
  }
```

**Update Task request body (v1 → v2):**

```diff
  PUT /tasks/1
  {
    "title": "Updated title",
-   "done": true
+   "completed": true
  }
```

**Migration:**

- Replace all references to the response field `done` with `completed`.
- Replace all uses of `done` in `PUT /tasks/{id}` request bodies with `completed`.
- Review any client-side logic that reads or writes `done` — the field
  name must change everywhere.

---

### 5. New Required Field: `project_id`

**Change:** Creating a task now requires `project_id`. Omitting it returns
HTTP 422 Unprocessable Entity. v1 accepted `title` alone.

```diff
  // v1 — title only
  POST /tasks
  {
    "title": "New task"
  }

  // v2 — title + required project_id
  POST /v2/tasks
  {
    "title": "New task",
+   "project_id": "proj_abc123"
  }
```

**Migration:**

- Provision a project in the Zrb console (or via the projects API, if
  available) before creating tasks.
- Add `project_id` to every `POST /tasks` call. The value is a string
  (see format `proj_*`).
- Decide how your application maps existing untracked tasks to a default
  project — you may want to create a "Legacy" project and assign all
  pre-migration tasks to it.

---

### 6. List Response Format: Bare Array → Paginated Envelope

**Change:** `GET /tasks` no longer returns a bare JSON array. It returns
a paginated envelope with an `items` array, a `total` count, and a
`next_cursor` for fetching the next page. The default page size is 20.

```diff
  // v1 — bare array
- [
-   {"id": 1, "title": "Buy milk", "done": false},
-   {"id": 2, "title": "Ship v1", "done": true}
- ]

  // v2 — paginated envelope
+ {
+   "items": [
+     {"id": "a1b2...", "title": "Buy milk", "completed": false},
+     {"id": "c3d4...", "title": "Ship v1", "completed": true}
+   ],
+   "total": 42,
+   "next_cursor": "cursor_xyz"
+ }
```

**Migration:**

- Replace array indexing (e.g., `response[0]`) with `response.items[0]`.
- If your code reads the total count from the array length
  (`response.length`), switch to `response.total`.
- To iterate through all tasks, use cursor-based pagination: pass
  `?cursor=<next_cursor>` to fetch subsequent pages until
  `next_cursor` is absent or `null`.

```diff
  // v1 pagination (assumed all-in-one)
- const tasks = await fetch("/tasks").then(r => r.json());
- tasks.forEach(t => process(t));

  // v2 cursor pagination
+ let cursor = null;
+ do {
+   const url = cursor
+     ? `/v2/tasks?cursor=${cursor}`
+     : `/v2/tasks`;
+   const page = await fetch(url).then(r => r.json());
+   page.items.forEach(t => process(t));
+   cursor = page.next_cursor;
+ } while (cursor);
```

---

## Summary of All Breaking Changes

| # | Change | v1 | v2 | Error if unchanged |
|---|--------|----|----|--------------------|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` | 404 or 405 |
| 2 | Auth header | `X-Auth-Token` | `Authorization: Bearer` | 401 |
| 3 | Task `id` type | integer | UUID string | 404 |
| 4 | Field `done` → `completed` | `"done": true` | `"completed": true` | silently ignored |
| 5 | `project_id` required | omitted | `"project_id": "proj_..."` | 422 |
| 6 | List format | bare array | paginated envelope | parse error |

---

## Step-by-Step Migration Checklist

- [ ] **Update endpoint URLs** — prepend `/v2` to all API paths.
- [ ] **Provision Bearer token** — obtain a new v2 token from the Zrb
      console.
- [ ] **Replace auth header** — switch from `X-Auth-Token` to
      `Authorization: Bearer <token>` in every request.
- [ ] **Update `id` handling** — change storage, comparisons, and URL
      construction from integer to UUID string.
- [ ] **Rename `done` to `completed`** — update all response parsing and
      request body construction.
- [ ] **Add `project_id` to task creation** — create a project first,
      then include `"project_id"` in every `POST /v2/tasks` body.
- [ ] **Rewrite list consumption** — unwrap the paginated envelope,
      replace `response[n]` with `response.items[n]`, and implement
      cursor-based pagination if you need more than one page.
- [ ] **Run integration tests** — exercise every endpoint against a v2
      staging environment and verify correct HTTP status codes, response
      shapes, and auth handling.

---

## Upgrade Command

```bash
pip install --upgrade zrb
```

After upgrading, update your client code per the checklist above. The v1
endpoints will continue to serve existing traffic for a deprecation window
(see the Zrb changelog for the sunset date), but new features and fixes
will target v2 only.
