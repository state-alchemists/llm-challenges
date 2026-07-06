# Zrb v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication conventions. This guide covers every breaking change between v1 and v2, with before/after examples for each one.

## Breaking Changes at a Glance

| # | Area | v1 | v2 |
|---|------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication | `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |
| 3 | Task ID type | integer | UUID string |
| 4 | Task field | `done` | `completed` |
| 5 | Task creation | `project_id` optional | `project_id` **required** |
| 6 | List response | bare array | paginated envelope |

---

## 1. Endpoint Prefix

All endpoints are now prefixed with `/v2/`. Requests to the old paths return `404`.

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

**Action:** Prefix all URL paths with `/v2/`.

---

## 2. Authentication Header

The `X-Auth-Token` header is replaced by the standard `Authorization: Bearer` scheme. Existing `X-Auth-Token` requests will receive HTTP 401.

**Before (v1):**

```http
X-Auth-Token: sk_live_abc123
```

**After (v2):**

```http
Authorization: Bearer zrb_live_abc123
```

Token values may also differ — obtain a v2 bearer token from the dashboard or via the `zrb auth token` CLI command.

**Action:** Replace `X-Auth-Token` headers with `Authorization: Bearer`. Issue new tokens if necessary.

---

## 3. Task ID Type: Integer → UUID String

Task IDs are now UUIDv4 strings instead of auto-incrementing integers. Existing integer IDs are **not reused** — every task was assigned a new UUID on migration.

**Before (v1):**

```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2):**

```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

**Action:**
- Update any code that assumes `id` is an integer (type checks, serialization, arithmetic).
- Update stored references (database foreign keys, cache keys, or URL fragments that hardcode v1 IDs).
- Look up the new UUID for each migrated task using the task's `title` or your internal mapping.

**Watch out:** Constructed URLs like `/tasks/42` are doubly broken — they use both the wrong prefix and the wrong ID type.

---

## 4. Field Rename: `done` → `completed`

The boolean completion field is renamed from `done` to `completed`. The old field no longer appears in responses and is rejected on write.

**Read (v1 → v2):**

```python
# v1
task["done"]   # True or False

# v2
task["completed"]   # True or False
```

**Write (v1 → v2):**

```python
# v1
requests.put("/tasks/42", json={"done": True})

# v2
requests.put("/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890", json={"completed": True})
```

**Action:** Rename all references to `done` → `completed` in request payloads and response parsing.

---

## 5. Required Field: `project_id`

Task creation now requires `project_id`. Omitting it returns HTTP 422.

**Before (v1):**

```http
POST /tasks
Content-Type: application/json

{ "title": "Write tests" }
```

**After (v2):**

```http
POST /v2/tasks
Content-Type: application/json

{ "title": "Write tests", "project_id": "proj_abc123" }
```

**Action:**
- Obtain a `project_id` from the projects endpoint (`GET /v2/projects`) or the dashboard.
- Add `project_id` to every `POST /v2/tasks` call.
- `project_id` is also returned in list/get responses — no action needed for reads.

---

## 6. List Response: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. All listing responses now use a paginated envelope.

**Before (v1):**

```python
resp = requests.get("/tasks")
tasks = resp.json()       # bare list — works directly
# [{"id": 1, "title": "Buy milk", "done": false}, ...]
```

**After (v2):**

```python
resp = requests.get("/v2/tasks", params={"limit": 20})
body = resp.json()
tasks = body["items"]         # ← nested under "items"
total = body["total"]         # total count across all pages
next_cursor = body.get("next_cursor")  # None on last page

# Paginate:
while next_cursor:
    resp = requests.get("/v2/tasks", params={"cursor": next_cursor, "limit": 20})
    body = resp.json()
    tasks.extend(body["items"])
    next_cursor = body.get("next_cursor")
```

**Action:**
- Access `body["items"]` instead of reading the response directly.
- Use `?cursor=` and `?limit=` to paginate; v2 does not support `?page=` or `?offset=`.
- The default page size is 20; set `?limit=` explicitly for a different size.

---

## Endpoint Reference

| Operation | v1 URL | v2 URL | What Changed |
|-----------|--------|--------|-------------|
| List tasks | `GET /tasks` | `GET /v2/tasks` | Response envelope, query params |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` | URL prefix, `id` is now a UUID |
| Create task | `POST /tasks` | `POST /v2/tasks` | URL prefix, `project_id` required |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` | URL prefix, field `completed` not `done` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` | URL prefix |

---

## Migration Checklist

- [ ] **Update base URL** — prefix all API paths with `/v2/`.
- [ ] **Rotate credentials** — replace `X-Auth-Token` with `Authorization: Bearer`; issue new tokens.
- [ ] **Migrate stored task IDs** — update any database columns, cache keys, or URL templates that hold integer task IDs to store UUID strings.
- [ ] **Rename `done` to `completed`** — update all request payloads, response parsers, and type definitions.
- [ ] **Add `project_id` to create calls** — obtain a project ID and include it in every `POST /v2/tasks` body.
- [ ] **Refactor list response handling** — unwrap `items`, `total`, and `next_cursor` from the paginated envelope.
- [ ] **Update error handling** — watch for HTTP 401 (bad auth), 422 (missing `project_id`), and 404 (wrong prefix or ID type).
- [ ] **Test against your v2 staging environment** — run your test suite against v2 before deploying to production.

---

## Upgrade

```bash
# Install or upgrade to Zrb v2
pip install --upgrade zrb>=2.0.0
```

After upgrading, verify your client version:

```bash
zrb --version
# zrb 2.x.x
```
