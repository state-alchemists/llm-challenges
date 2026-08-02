# Zrb Task API — v2 Migration Guide

Zrb v2 is here, and it ships six breaking changes to the Task API. If you already have v1 clients, this guide walks through each change, what breaks, and what the fixed code looks like. Full details for both versions live in [`v1_spec.md`](./v1_spec.md) and [`v2_spec.md`](./v2_spec.md).

In the examples below, `https://api.example.com` is your API base URL, `$ZRB_API_KEY` is your v1 API key, and `$ZRB_API_TOKEN` is your v2 bearer token.

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication | `X-Auth-Token` header | `Authorization: Bearer` header |
| 3 | Task `id` type | integer | UUID string |
| 4 | Completion field | `done` | `completed` |
| 5 | Create requires `project_id` | optional/absent | required (422 if missing) |
| 6 | List responses | bare array | paginated envelope |

---

## 1. Endpoint prefix: `/v2/`

Every endpoint is now prefixed with `/v2/`. Requests to the old paths — including valid v2 auth — will not resolve.

**Before (v1):**

```bash
curl https://api.example.com/tasks \
  -H "X-Auth-Token: $ZRB_API_KEY"
```

**After (v2):**

```bash
curl https://api.example.com/v2/tasks \
  -H "Authorization: Bearer $ZRB_API_TOKEN"
```

(Header differences in these examples are covered in §2.) Update your base path or URL builder once and it applies to every endpoint: list, get, create, update, and delete.

---

## 2. Authentication: Bearer token replaces `X-Auth-Token`

The `X-Auth-Token` header is gone. All requests must use a standard Bearer token. Requests that still send `X-Auth-Token` are rejected with **HTTP 401** — you cannot mix the two.

**Before (v1):**

```bash
curl https://api.example.com/tasks \
  -H "X-Auth-Token: $ZRB_API_KEY"
```

**After (v2):**

```bash
curl https://api.example.com/v2/tasks \
  -H "Authorization: Bearer $ZRB_API_TOKEN"
```

Issuing v2 tokens happens through your normal account/workspace credentials — see the v2 reference for token provisioning. Rotate old v1 keys out of config files, CI secrets, and documentation.

---

## 3. Task `id` is now a UUID string

Task IDs changed from auto-incrementing integers to UUID strings. This affects the Task object, the `{id}` path parameter on get/update/delete, and any client logic that treats IDs as numbers.

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

Path parameters follow the same change:

**Before (v1):**

```bash
curl https://api.example.com/tasks/42 \
  -H "X-Auth-Token: $ZRB_API_KEY"
```

**After (v2):**

```bash
curl https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer $ZRB_API_TOKEN"
```

Treat IDs as opaque strings: store them as strings, never parse or increment them, and drop any `Number(id)` / `parseInt(id)` coercion in your clients and database columns.

---

## 4. `done` renamed to `completed`

The Task field `done` is renamed to `completed`. The field no longer exists under its old name — request payloads must send `completed`, and response parsing must read `completed`.

**Before (v1):**

```bash
curl -X PUT https://api.example.com/tasks/42 \
  -H "X-Auth-Token: $ZRB_API_KEY" \
  -d '{"done": true}'
```

**After (v2):**

```bash
curl -X PUT https://api.example.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer $ZRB_API_TOKEN" \
  -d '{"completed": true}'
```

Update both sides of your integration — the bodies you send (create/update) and the fields you read back (list/get/update responses). Rename `done` in your types, models, and any UI bindings.

---

## 5. `project_id` is now required when creating tasks

Creating a task now requires a `project_id`. Omitting it returns **HTTP 422**. You must obtain a valid project ID for your workspace and send it with every create.

**Before (v1):**

```bash
curl -X POST https://api.example.com/tasks \
  -H "X-Auth-Token: $ZRB_API_KEY" \
  -d '{"title": "New task title"}'
```

**After (v2):**

```bash
curl -X POST https://api.example.com/v2/tasks \
  -H "Authorization: Bearer $ZRB_API_TOKEN" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

Handle the 422 explicitly in your create path — treat it as a client-side error (missing/invalid `project_id`), not a server failure, and surface a useful message. Note the created Task now carries `project_id` in its response too; store it if you need to create related tasks later.

---

## 6. List responses are paginated envelopes

List endpoints no longer return a bare array. They return an envelope with `items`, `total`, and a `next_cursor`. Pagination is cursor-based: pass `?cursor=<next_cursor>` to fetch the next page, and use `?limit=` to control page size (default **20**). There is no page-number or offset parameter.

**Before (v1):**

```bash
curl https://api.example.com/tasks \
  -H "X-Auth-Token: $ZRB_API_KEY"
```

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2):**

```bash
curl "https://api.example.com/v2/tasks?limit=20&cursor=cursor_xyz" \
  -H "Authorization: Bearer $ZRB_API_TOKEN"
```

```json
{
  "items": [],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Any code that consumed the list as an array must change. Iterate with the cursor until `next_cursor` is null or empty:

**Before (v1):**

```python
tasks = response.json()      # list
total = len(tasks)           # not the true total once paginated
first_id = tasks[0]["id"]    # int
```

**After (v2):**

```python
page = response.json()       # dict
tasks = page["items"]
total = page["total"]        # total across all pages, not just this one
next_cursor = page["next_cursor"]
if next_cursor:
    # fetch f"{BASE}/v2/tasks?cursor={next_cursor}" for the next page
```

---

## What Did Not Change

To keep the migration focused, these are unchanged in v2:

- `title` and `created_at` field semantics
- `POST /v2/tasks` returns **201** with the created Task
- `DELETE /v2/tasks/{id}` returns **204 No Content**
- `PUT /v2/tasks/{id}` accepts all fields as optional
- `GET /v2/tasks/{id}` returns **404** for missing tasks

---

## Step-by-Step Migration Checklist

- [ ] **1. Audit the v1 surface.** Grep your codebase for `X-Auth-Token`, `/tasks` (any call missing `/v2/`), `done`, and integer-typed `id` handling.
- [ ] **2. Migrate authentication.** Replace `X-Auth-Token: <key>` with `Authorization: Bearer <token>` in every client, SDK config, CI secret, and example. Confirm old-header requests return 401.
- [ ] **3. Prefix all endpoints with `/v2/`.** Update base URLs, path builders, and any hardcoded routes.
- [ ] **4. Rename `done` → `completed`.** Update request payloads, response parsing, types, models, and UI bindings.
- [ ] **5. Treat `id` as an opaque UUID string.** Update types (`number` → `string`), remove arithmetic/coercion, and change any integer-keyed storage.
- [ ] **6. Add `project_id` to creates.** Include it in every `POST /v2/tasks` payload and handle 422 responses as client-side errors.
- [ ] **7. Rewrite list consumers for the envelope.** Read `items` / `total` / `next_cursor`, and implement cursor-based pagination in place of page numbers.
- [ ] **8. Update types, mocks, fixtures, and docs.** Sync your OpenAPI specs, generated clients, and internal documentation to the v2 shapes.
- [ ] **9. Test against staging.** Verify auth (401 on old header), CRUD round-trips, `project_id` validation, and multi-page listing.
- [ ] **10. Deploy and monitor.** Roll out after the upgrade below, then watch for 401/422 spikes from stale clients.

---

## Upgrade to v2

```bash
pip install --upgrade zrb
```

Verify the install reports a v2 release, then walk the checklist above against your staging environment before pointing production traffic at the new API.
