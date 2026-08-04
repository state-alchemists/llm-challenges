# Zrb v2 Migration Guide

Zrb v2 ships several breaking changes to the Task API. This guide covers everything that changes between v1 (`v1_spec.md`) and v2 (`v2_spec.md`), with before/after examples for each break, so you can migrate existing v1 clients with minimal guesswork.

There are **six breaking changes**:

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint path prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token` | `Authorization: Bearer` |
| 3 | Task `id` type | integer | UUID string |
| 4 | Field rename | `done` | `completed` |
| 5 | Task creation | `project_id` optional | `project_id` required (422 if missing) |
| 6 | List responses | bare array | paginated envelope |

Each is detailed below in the same order.

---

## 1. All endpoints are prefixed with `/v2/`

Every endpoint moved under the `/v2/` path. Old v1 paths do not resolve in v2.

| Endpoint | v1 | v2 |
|----------|----|----|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**

```bash
curl https://api.example.com/tasks \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**

```bash
curl https://api.example.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>"
```

Update the base path in every client, SDK configuration, and hardcoded URL. The auth header changed at the same time — see the next section.

---

## 2. Authentication header changed

`X-Auth-Token` is gone. v2 requires a Bearer token in the `Authorization` header. Requests that still send `X-Auth-Token` receive **HTTP 401** — the v1 key is not accepted as a Bearer token.

**Before (v1):**

```bash
curl https://api.example.com/tasks \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**

```bash
curl https://api.example.com/v2/tasks \
  -H "Authorization: Bearer <your_api_token>"
```

Obtain a v2 token, then update every place the credential is stored — environment files, CI secrets, and config managers. Once migration is complete, rotate/revoke the old v1 keys.

---

## 3. Task `id` changed from integer to UUID string

The task `id` is now a UUID string instead of an integer. This affects response payloads and every path parameter that takes an ID.

**Before (v1) — task object:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) — task object:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

URLs that take an ID change too:

**Before (v1):**

```bash
curl https://api.example.com/tasks/42 \
  -H "X-Auth-Token: <your_api_key>"
```

**After (v2):**

```bash
curl https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <your_api_token>"
```

Treat IDs as opaque strings: no integer math, store and compare as text. If you persisted v1 integer IDs in a database, cache, or logs, those values will not match v2 IDs — plan a mapping or re-fetch and re-key your data during migration.

---

## 4. `done` renamed to `completed`

The completion flag is now `completed`. This applies to both responses and request bodies (create and update payloads).

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

Update reads (deserializers, display logic, any `task.done` checks) and writes (create and update payloads) together. Grep your codebase for `done` and replace it with `completed` where it refers to task state; `title` and `created_at` are unchanged.

---

## 5. Task creation requires `project_id`

`POST /v2/tasks` now requires a `project_id`. Omitting it returns **HTTP 422**. Every task must belong to a project.

**Before (v1):**

```json
{
  "title": "New task title"
}
```

**After (v2):**

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

Obtain valid project IDs up front and thread them through every code path that creates tasks — interactive forms, batch jobs, and tests included. Validate the project ID before calling the API so a missing/invalid one surfaces as a clean input error instead of a 422 from the server.

---

## 6. List endpoints return a paginated envelope

List responses are no longer bare arrays. v2 wraps results in `{items, total, next_cursor}` and pages with cursor-based pagination. `limit` (default 20) and `cursor` are accepted as query parameters.

**Before (v1) — `GET /tasks`:**

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2) — `GET /v2/tasks`:**

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

Client code that iterated the response directly must now read `items`. If you need all results, follow `next_cursor` — pass it back as `?cursor=<next_cursor>` — until the API returns no cursor.

**Before (v1):**

```js
const tasks = await fetch("https://api.example.com/tasks", { headers })
  .then(r => r.json());
for (const task of tasks) { /* ... */ }
```

**After (v2):**

```js
let cursor;
do {
  const url = "https://api.example.com/v2/tasks?limit=20"
    + (cursor ? `&cursor=${cursor}` : "");
  const page = await fetch(url, { headers }).then(r => r.json());
  for (const task of page.items) { /* ... */ }
  cursor = page.next_cursor;
} while (cursor);
```

---

## What didn't change

- `title` and `created_at` field names and formats
- `GET /v2/tasks/{id}` returns a single task or `404`
- Create returns HTTP 201; delete returns HTTP 204
- Update semantics: `PUT` with all fields optional

---

## Migration checklist

Work through these in order, ideally against a staging environment before touching production.

1. **Upgrade Zrb** to v2 (see the Upgrade section below).
2. **Switch authentication** — replace `X-Auth-Token` with `Authorization: Bearer <token>` in every client, CI job, and config store. Verify: a request with the old header returns 401.
3. **Update base paths** — prefix every endpoint with `/v2/` (all five endpoints from Section 1).
4. **Treat IDs as opaque strings** — update deserializers, comparisons, and URL construction; re-key any stored v1 integer IDs (Section 3).
5. **Rename `done` → `completed`** everywhere you read or write task state (Section 4). Verify: `PUT` with `completed` toggles the flag.
6. **Provide `project_id` on every create** — collect and validate it before `POST /v2/tasks` (Section 5). Verify: omitting it returns 422.
7. **Rewrite list handling** — read `items` from the envelope and follow `next_cursor` for pagination (Section 6). Verify: `GET /v2/tasks` returns the envelope shape.
8. **Smoke-test the full CRUD flow** — list, get, create, update, delete against staging.
9. **Rotate credentials and ship** — revoke v1 API keys, deploy, and monitor for 401s (auth) and 422s (missing `project_id`).

## Upgrade

```bash
pip install --upgrade zrb
```
