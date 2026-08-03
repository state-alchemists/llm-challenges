# Zrb Task API — v1 to v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. Six behaviors from v1 are breaking; every one of them is covered below with a before/after example. Plan for a coordinated client release: v1 and v2 do **not** interoperate — requests with the old auth header are rejected with HTTP 401, and the previous unversioned paths no longer exist.

This guide assumes you are already shipping against v1 and know the task object and endpoints.

## Breaking Changes at a Glance

1. All endpoints are prefixed with `/v2/`
2. `X-Auth-Token` header replaced by `Authorization: Bearer`
3. Task `id` changed from integer to UUID string
4. Task field `done` renamed to `completed`
5. Task creation now requires `project_id`
6. List endpoints return a paginated envelope instead of a bare array

---

## 1. Endpoint URLs are prefixed with `/v2/`

Every endpoint moves under `/v2`. The previous paths no longer exist.

Before:

```bash
curl https://api.zrb.example/tasks
curl https://api.zrb.example/tasks/42
curl -X POST https://api.zrb.example/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title": "New task title"}'
```

After:

```bash
curl https://api.zrb.example/v2/tasks
curl https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X POST https://api.zrb.example/v2/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

Update any hardcoded URLs, base-path configuration, and client-side URL construction.

---

## 2. Authentication header changed to Bearer tokens

The `X-Auth-Token` header is gone. Requests that still send it receive **HTTP 401**. Use a Bearer token instead — and note the token is no longer a plain API key, so rotate credentials as part of the migration.

Before:

```bash
curl https://api.zrb.example/tasks \
  -H 'X-Auth-Token: your_api_key'
```

After:

```bash
curl https://api.zrb.example/v2/tasks \
  -H 'Authorization: Bearer your_api_token'
```

If you use an SDK or HTTP client that injects headers globally (e.g. an `Authorization` interceptor, a `headers` dict, or a session default), change it in one place rather than per call site.

---

## 3. Task `id` is now a UUID string

Integer IDs are replaced by UUID strings. This ripples further than the JSON shape: the value flows into URL paths, local caches, and database columns.

Before:

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

After:

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Practical consequences:

- **URL paths**: `GET /tasks/42` becomes `GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890`.
- **Client models**: stop parsing `id` as a number. Treat it as an opaque string — do not assume order or sortability.
- **Storage**: widen any column or field that previously stored integer IDs, and plan a data migration for IDs you persist or reference across systems.
- **Caching**: keys built from numeric IDs must be re-derived, or caches will miss.

```python
# Before
task_id = int(response.json()["id"])  # 42

# After
task_id = response.json()["id"]  # "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

---

## 4. Task field `done` renamed to `completed`

The boolean flag is now `completed`. This affects **both directions**: responses read it under the new name, and `PUT` request bodies must send it.

Before:

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

After:

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false
}
```

Update request bodies too:

```bash
# Before
curl -X PUT https://api.zrb.example/tasks/42 \
  -H 'Content-Type: application/json' \
  -d '{"done": true}'

# After
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H 'Content-Type: application/json' \
  -d '{"completed": true}'
```

Grep your codebase for `done` before you ship — it commonly hides in serializers, UI state, and test fixtures.

---

## 5. Task creation requires `project_id`

`POST /tasks` no longer accepts just a title. `project_id` is now a **required** field of the request body and of every task object; omitting it returns **HTTP 422**.

Before:

```bash
curl -X POST https://api.zrb.example/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title": "New task title"}'
```

After:

```bash
curl -X POST https://api.zrb.example/v2/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

You now need a project before you can create a task. Add a "list projects" or "get project" step to your provisioning flow, and treat `422` from create as a missing-`project_id` signal.

---

## 6. List endpoints return a paginated envelope

`GET /tasks` returned a bare array. All list endpoints now return an envelope with `items`, `total`, and `next_cursor` — the array moved under `items`.

Before:

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

After:

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6a1b2-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Pagination is cursor-based. Fetch the next page by passing the cursor back:

```bash
curl 'https://api.zrb.example/v2/tasks?cursor=cursor_xyz&limit=20'
```

- `cursor` — optional, from the previous response's `next_cursor`
- `limit` — max results per page, default `20`
- An absent `next_cursor` means you are on the last page

Update every consumer that indexes the response directly (`response[0]`, `for task in data`):

```python
# Before
tasks = response.json()

# After
tasks = response.json()["items"]
```

---

## Migration Checklist

Work through these in order. Items 1–3 are prerequisites; 4–7 are the code changes; 8 is the cutover.

- [ ] **1. Issue and distribute Bearer tokens.** `X-Auth-Token` keys stop working in v2; every client needs a token.
- [ ] **2. Enumerate your call sites.** Grep for `/tasks`, `X-Auth-Token`, `done`, and `"id"` across clients, SDKs, scripts, and tests so nothing is missed.
- [ ] **3. Plan the ID migration.** Decide how stored integer IDs map to UUIDs, and widen any local storage that held `id` as a number.
- [ ] **4. Update authentication.** Replace `X-Auth-Token` with `Authorization: Bearer` in one central place if possible (session/interceptor default).
- [ ] **5. Prefix all URLs with `/v2/`.** Update base paths and any hardcoded endpoint strings.
- [ ] **6. Update task models and payloads.** Rename `done` → `completed` in both directions; treat `id` as an opaque string; stop assuming numeric IDs.
- [ ] **7. Handle pagination.** Read list responses as `items`/`total`/`next_cursor`; loop with `?cursor=` until `next_cursor` is absent; respect `limit`.
- [ ] **8. Require `project_id` on create.** Provision a project first and send `project_id` with every `POST`; handle `422` as a missing-field error.
- [ ] **9. Update tests and fixtures.** Every fixture that used `done`, bare-array lists, integer IDs, or the old header must be regenerated.
- [ ] **10. Validate against the v2 API.** Run your full suite against v2 and confirm 401/404 paths are gone before cutover.

## Upgrade

```bash
pip install --upgrade zrb
```

Installed via `pipx`? Upgrade with:

```bash
pipx upgrade zrb
```

Verify the new version, then run the checklist above against the v2 API before promoting the change.
