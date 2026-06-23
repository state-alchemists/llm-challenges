# Zrb Task API v1 → v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. If you are currently integrating with v1, this guide lists every breaking change and the exact code changes required to migrate.

> **Compatibility note:** v1 endpoints will continue to respond, but they may be deprecated in a future release. Migrate proactively to avoid service interruptions.

---

## Breaking Changes

### 1. Endpoint prefix changed to `/v2/`

All endpoints are now prefixed with `/v2/`. Requests to the old unprefixed paths will hit v1 (which remains available) or return 404, depending on your gateway configuration.

**Before (v1):**

```bash
curl -X GET https://api.zrb.example/tasks
curl -X POST https://api.zrb.example/tasks
curl -X PUT https://api.zrb.example/tasks/42
curl -X DELETE https://api.zrb.example/tasks/42
```

**After (v2):**

```bash
curl -X GET https://api.zrb.example/v2/tasks
curl -X POST https://api.zrb.example/v2/tasks
curl -X PUT https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
curl -X DELETE https://api.zrb.example/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication header changed to Bearer token

The custom `X-Auth-Token` header is no longer accepted in v2. You must send a standard `Authorization: Bearer <token>` header. Requests with `X-Auth-Token` will receive HTTP 401.

**Before (v1):**

```bash
curl -H "X-Auth-Token: <your_api_key>" \
  https://api.zrb.example/tasks
```

**After (v2):**

```bash
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.example/v2/tasks
```

> **Action:** Replace your existing token storage key name if you were storing the header name alongside the secret.

---

### 3. Task `id` changed from integer to UUID string

Task identifiers are now UUID strings instead of auto-incrementing integers. Any code that assumes `id` is a number, performs arithmetic on it, or stores it in an integer column must be updated.

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

> **Impact:** Database schemas, path parameters, and equality checks must treat `id` as a string.

---

### 4. Task field `done` renamed to `completed`

The boolean flag indicating whether a task is finished has been renamed from `done` to `completed`. Sending `done` in a request body or reading it from a response will fail.

**Before (v1) — request body:**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) — request body:**

```json
{
  "title": "Updated title",
  "completed": true
}
```

**Before (v1) — client deserialization:**

```python
if task["done"]:
    print("Finished")
```

**After (v2) — client deserialization:**

```python
if task["completed"]:
    print("Finished")
```

---

### 5. Task creation now requires `project_id`

Creating a task without a `project_id` now returns HTTP 422. You must obtain a project identifier (via the Projects API or your dashboard) and include it in every `POST /v2/tasks` request.

**Before (v1):**

```bash
curl -X POST https://api.zrb.example/tasks \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: <your_api_key>" \
  -d '{"title": "New task title"}'
```

**After (v2):**

```bash
curl -X POST https://api.zrb.example/v2/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_api_token>" \
  -d '{
    "title": "New task title",
    "project_id": "proj_abc123"
  }'
```

> **Impact:** You may need to add a project selection step to your UI or default the `project_id` from environment configuration.

---

### 6. List endpoints return a paginated envelope

`GET /v2/tasks` no longer returns a bare array. It returns a paginated envelope containing `items`, `total`, and `next_cursor`. You must update any code that iterated directly over the response body.

**Before (v1):**

```python
import requests

response = requests.get("https://api.zrb.example/tasks", headers={"X-Auth-Token": key})
tasks = response.json()
for task in tasks:
    print(task["title"])
```

**After (v2):**

```python
import requests

response = requests.get(
    "https://api.zrb.example/v2/tasks",
    headers={"Authorization": f"Bearer {token}"}
)
data = response.json()
tasks = data["items"]
for task in tasks:
    print(task["title"])

# Fetch next page if present
if data.get("next_cursor"):
    next_response = requests.get(
        "https://api.zrb.example/v2/tasks",
        headers={"Authorization": f"Bearer {token}"},
        params={"cursor": data["next_cursor"]}
    )
```

> **Impact:** Any code that assumes `response.json()` is a list will fail with a TypeError or equivalent.

---

## Migration Checklist

Use this checklist to ensure you have addressed every breaking change before deploying to production.

- [ ] **Update base URLs:** Add `/v2/` prefix to all endpoint calls (`/tasks` → `/v2/tasks`).
- [ ] **Rotate authentication:** Replace `X-Auth-Token` header with `Authorization: Bearer <token>`.
- [ ] **Migrate ID storage:** Change `id` fields from integer types to string/UUID types in your database, models, and validation schemas.
- [ ] **Rename `done` → `completed`:** Update request payloads, response parsing, and UI bindings that reference the `done` field.
- [ ] **Add `project_id` to task creation:** Ensure `POST /v2/tasks` payloads include a valid `project_id`.
- [ ] **Adapt list handling:** Wrap list responses in the paginated envelope (`items`, `total`, `next_cursor`) and implement cursor pagination if you paginate.
- [ ] **Update tests and fixtures:** Replace integer IDs and bare arrays in mocks/stubs with UUID strings and paginated envelopes.
- [ ] **Smoke-test in staging:** Run your integration test suite against the v2 endpoints before production rollout.

---

## Upgrade Command

To install the v2 CLI and verify the version:

```bash
npm install -g @zrb/cli@latest
zrb --version   # Expected: 2.x.x or higher
```

If you encounter unexpected behavior after upgrading, open an issue at `https://github.com/state-alchemists/zrb/issues` with the `--verbose` output attached.
