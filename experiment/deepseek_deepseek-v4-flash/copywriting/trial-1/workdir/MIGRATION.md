# Zrb CLI v1 → v2 Migration Guide

This guide walks experienced v1 developers through the breaking changes in Zrb v2. The v2 release changes the Task API surface that your code talks to: every endpoint moves, the authentication scheme changes, task IDs become UUIDs, `done` is renamed, task creation requires a project, and list responses are paginated.

Each breaking change below has a before/after example. If you only take one thing away: read the table, fix the six items, then work the checklist at the end.

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Base path | `/tasks` | `/v2/tasks` |
| 2 | Auth header | `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |
| 3 | Task ID type | integer (`42`) | UUID string (`"a1b2c3d4-…"`) |
| 4 | Completion field | `done` | `completed` |
| 5 | Create payload | `title` only | `title` + `project_id` (422 if omitted) |
| 6 | List response | bare array | `{items, total, next_cursor}` envelope, 20 per page by default |

---

## 1. All Endpoints Move Under `/v2/`

Every endpoint is now prefixed with `/v2/`. Update base URLs, SDK configurations, and any hardcoded paths.

**Before:**

```bash
curl https://api.example.com/tasks
```

**After:**

```bash
curl https://api.example.com/v2/tasks
```

Full endpoint mapping:

| v1 | v2 |
|----|----|
| `GET /tasks` | `GET /v2/tasks` |
| `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| `POST /tasks` | `POST /v2/tasks` |
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

---

## 2. Authentication: Bearer Tokens Replace `X-Auth-Token`

The `X-Auth-Token` header is gone. Requests that still send it receive **HTTP 401**. Use the `Authorization: Bearer` scheme instead.

**Before:**

```bash
curl -H "X-Auth-Token: your_api_key" https://api.example.com/tasks
```

**After:**

```bash
curl -H "Authorization: Bearer your_api_token" https://api.example.com/v2/tasks
```

Provision a v2 bearer token through your credential workflow before migrating — the old API key format will not authenticate.

---

## 3. Task IDs Are Now UUID Strings

`id` changed from an auto-assigned integer to a UUID string. This breaks path parameters, stored IDs, and any code that compares or computes on numeric IDs.

**Before:**

```bash
curl https://api.example.com/tasks/42
```

```json
{"id": 42, "title": "Write tests", "done": false}
```

**After:**

```bash
curl https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false}
```

**Before:**

```js
if (task.id === 42) { /* … */ }
```

**After:**

```js
if (task.id === "a1b2c3d4-e5f6-7890-abcd-ef1234567890") { /* … */ }
```

Audit anywhere an ID is stored or built: database columns, caches, dedup keys, URL builders, and message payloads. If you persisted v1 integer IDs, you will need to map them to the new UUIDs.

---

## 4. `done` Is Renamed to `completed`

The completion flag is now `completed` in both responses and update request bodies. Update every read and write.

**Before:**

```json
{"id": 42, "title": "Write tests", "done": true}
```

**After:**

```json
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": true}
```

**Before:**

```bash
curl -X PUT https://api.example.com/tasks/42 \
  -H "X-Auth-Token: your_api_key" \
  -d '{"done": true}'
```

**After:**

```bash
curl -X PUT https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer your_api_token" \
  -d '{"completed": true}'
```

Grep your codebase for `done` — `.done`, `["done"]`, and `"done":` in payloads — and rename all of them.

---

## 5. Task Creation Now Requires `project_id`

`POST /v2/tasks` requires a `project_id`. Omitting it returns **HTTP 422**. Decide where each create path gets its project ID (config, workspace context, user input) and validate before calling.

**Before:**

```bash
curl -X POST https://api.example.com/tasks \
  -H "X-Auth-Token: your_api_key" \
  -d '{"title": "New task title"}'
```

**After:**

```bash
curl -X POST https://api.example.com/v2/tasks \
  -H "Authorization: Bearer your_api_token" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

v1 tasks had no project association. How existing tasks are assigned to projects is not covered by the v2 reference — confirm with the platform whether they are migrated automatically or must be re-created.

---

## 6. List Responses Are Paginated

List endpoints no longer return a bare array. `GET /v2/tasks` returns an envelope, and pagination is on by default with `limit` defaulting to **20** — a client that does not paginate only ever sees the first page.

**Before:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**After:**

```json
{
  "items": [
    {"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false},
    {"id": "b2c3d4e5-f6a7-8901-bcde-f12345678901", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Before:**

```js
const tasks = await getTasks();          // array
tasks.forEach((t) => console.log(t.title));
```

**After:**

```js
let cursor;
do {
  const page = await getTasks({ cursor, limit: 50 });
  page.items.forEach((t) => console.log(t.title));
  cursor = page.next_cursor;
} while (cursor);
```

Pass `?cursor=<next_cursor>` to fetch the next page and stop when the cursor is exhausted.

---

## What Hasn't Changed

- `title` — string, unchanged
- `created_at` — ISO 8601 timestamp, unchanged
- `PUT /v2/tasks/{id}` still supports partial updates (all fields optional)
- Creating a task still returns HTTP 201 with the created object
- Deleting a task still returns HTTP 204 No Content
- HTTP verbs and the overall resource model are the same

---

## Step-by-Step Migration Checklist

- [ ] **Upgrade the CLI** to v2 (`pip install --upgrade zrb` — also in the final section).
- [ ] **Provision credentials**: a v2 bearer token and valid `project_id`(s).
- [ ] **Update base URLs** to the `/v2/` prefix in configs, env vars, SDKs, and hardcoded paths.
- [ ] **Swap auth headers**: replace `X-Auth-Token` with `Authorization: Bearer <token>` everywhere.
- [ ] **Convert task IDs**: migrate stored IDs (DB schema, caches), fix path building, and replace numeric comparisons with string comparisons.
- [ ] **Rename `done` → `completed`** in all reads and update payloads; grep for `done` and fix every hit.
- [ ] **Add `project_id`** to every create call and handle the HTTP 422 error case.
- [ ] **Update list consumers** to read `items`, pass `limit`, and loop on `next_cursor`.
- [ ] **Update tests and fixtures** to v2 shapes; regenerate mocks and any OpenAPI-generated clients.
- [ ] **Verify on staging**: no 401s from stale auth, creates succeed with `project_id`, and pagination returns every task, not just the first 20.
- [ ] **Update internal docs** and any shared code snippets.

---

## Upgrade

Upgrade the Zrb CLI to v2:

```bash
pip install --upgrade zrb
```
