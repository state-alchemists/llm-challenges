# Zrb CLI v2 Migration Guide

Zrb v2 introduces projects, cursor-based pagination, and stricter authentication. Every breaking change is listed below with a before/after example so you can upgrade your codebase with confidence.

---

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoint prefix `/tasks` → `/v2/tasks` | All URL paths change |
| 2 | Auth header `X-Auth-Token` → `Authorization: Bearer` | Existing tokens rejected with 401 |
| 3 | Task `id` integer → UUID string | ID-dependent caching and references break |
| 4 | Field `done` → `completed` | Reads and writes using `done` are silently ignored |
| 5 | `project_id` required on create | `POST /v2/tasks` returns 422 without it |
| 6 | List response: bare array → paginated envelope | Parsing code must handle `{items, total, next_cursor}` |

---

## 1. Endpoint Prefix

**All** endpoints are now prefixed with `/v2/`. Requests to the old paths return 404.

**Before (v1):**

```bash
curl https://api.zrb.dev/tasks
```

```python
response = requests.get("https://api.zrb.dev/tasks/42")
```

**After (v2):**

```bash
curl https://api.zrb.dev/v2/tasks
```

```python
response = requests.get("https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890")
```

Update your API base URL or prefix all path arguments with `/v2/`.

---

## 2. Authentication Header

The `X-Auth-Token` header is no longer accepted. Use the standard `Authorization: Bearer` scheme instead. Requests with the old header receive HTTP 401 immediately.

**Before (v1):**

```http
X-Auth-Token: sk-abc123
```

```bash
curl https://api.zrb.dev/tasks \
  -H "X-Auth-Token: sk-abc123"
```

**After (v2):**

```http
Authorization: Bearer sk-abc123
```

```bash
curl https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer sk-abc123"
```

```python
# v1
headers = {"X-Auth-Token": token}

# v2
headers = {"Authorization": f"Bearer {token}"}
```

Your existing API key is valid — only the header name changes.

---

## 3. Task ID: Integer → UUID String

Task `id` is now a UUID v4 string instead of an auto-incrementing integer. This affects `GET`, `PUT`, and `DELETE` calls that reference a task by ID, as well as any local caches or databases that store task IDs.

**Before (v1):**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

```bash
curl https://api.zrb.dev/tasks/42
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

```bash
curl https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Migration tips:**
- If you store task IDs in a relational database, change the column type from `INTEGER` to `UUID` / `VARCHAR(36)`.
- Drop integer-based assumptions like `id > last_id` for ordering — use `created_at` instead.
- UUIDs cannot be incremented or guessed. Do not rely on sequential IDs.

---

## 4. Field Renamed: `done` → `completed`

The boolean field `done` is renamed to `completed` in all responses and write payloads. v2 ignores the old field name — writing `"done": true` has no effect.

**Before (v1):**

```json
// Response
{"id": 42, "title": "Write tests", "done": false}

// Create / Update payload
{"title": "Write tests", "done": true}
```

**After (v2):**

```json
// Response
{"id": "a1b2c3d4-...", "title": "Write tests", "completed": false, "project_id": "proj_abc123"}

// Create / Update payload
{"title": "Write tests", "completed": true, "project_id": "proj_abc123"}
```

```javascript
// v1
if (task.done) { /* ... */ }

// v2
if (task.completed) { /* ... */ }
```

Audit every read and write to the `done` field across your codebase and rename to `completed`.

---

## 5. `project_id` Now Required on Task Creation

All tasks must belong to a project. The `project_id` field is **required** on `POST /v2/tasks`. Omitting it returns HTTP 422 with a validation error. Existing tasks retain their data but do not have a `project_id` — you must assign one via an update before you can modify other fields.

**Before (v1):**

```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: sk-abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "Write tests"}'
# → 201 Created
```

**After (v2):**

```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer sk-abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "Write tests", "project_id": "proj_abc123"}'
# → 201 Created

curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer sk-abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "Missing project"}'
# → 422 Unprocessable Entity
```

```python
# v1
payload = {"title": "Write tests"}

# v2
payload = {"title": "Write tests", "project_id": "proj_abc123"}
```

1. Create your projects upfront (see the Projects API docs).
2. Pass `project_id` in every create request.
3. Patch existing v1 tasks that lack a `project_id` before they can be updated.

---

## 6. List Response: Paginated Envelope

List endpoints no longer return a bare array. The response is wrapped in a paginated envelope with metadata. Pagination uses cursor-based tokens rather than page numbers.

**Before (v1):**

```http
GET /tasks
```

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "2024-01-10T08:00:00Z"},
  {"id": 2, "title": "Ship v1",  "done": true,  "created_at": "2024-01-15T10:30:00Z"}
]
```

```javascript
// v1 — direct array access
const tasks = response.data;
tasks.forEach(t => console.log(t.title));
```

**After (v2):**

```http
GET /v2/tasks?limit=20&cursor=eyJpZCI6Mn0=
```

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "2024-01-10T08:00:00Z"},
    {"id": "e5f6a7b8-...", "title": "Ship v2",  "completed": true,  "project_id": "proj_abc123", "created_at": "2024-01-15T10:30:00Z"}
  ],
  "total": 42,
  "next_cursor": "abc123"
}
```

```javascript
// v2 — access through envelope
const { items, total, next_cursor } = response.data;
items.forEach(t => console.log(t.title));

// Fetch next page
if (next_cursor) {
  const next = await fetch(`/v2/tasks?cursor=${next_cursor}`);
}
```

**Response structure:**

| Field         | Type          | Description                              |
|---------------|---------------|------------------------------------------|
| `items`       | `Task[]`      | The page of task objects                 |
| `total`       | `number`      | Total number of tasks across all pages   |
| `next_cursor` | `string|null` | Pass as `?cursor=` for the next page     |

**Query parameters:**

| Param    | Type     | Default | Description                        |
|----------|----------|---------|------------------------------------|
| `cursor` | `string` | —       | Opaque cursor from the previous page |
| `limit`  | `number` | `20`    | Maximum items per page (1–100)     |

The `next_cursor` is an opaque string — do not construct or interpret it yourself. When `next_cursor` is `null` or absent, you have reached the last page.

---

## Migration Checklist

Follow these steps in order:

- [ ] **Update authentication header.** Replace `X-Auth-Token` with `Authorization: Bearer` in every request. Your existing API key continues to work.
- [ ] **Prefix all endpoints with `/v2/`.** Change `GET /tasks` → `GET /v2/tasks`, `POST /tasks` → `POST /v2/tasks`, etc.
- [ ] **Rename `done` to `completed`.** Search your codebase for `task.done`, `"done":`, and `done:` — replace each occurrence with `completed`. Update UI labels as well ("Done" → "Completed").
- [ ] **Handle UUID task IDs.** Stop assuming integer IDs. Change database column types, check ID-based comparison logic, and update any stored references that rely on integer format.
- [ ] **Add `project_id` to all task creation calls.** Create projects via the Projects API first, then pass the project ID. Patch existing tasks that lack `project_id`.
- [ ] **Update list-response parsing.** Replace bare-array access with envelope parsing. Expect `response.data.items` instead of `response.data`. Wire up cursor-based pagination for large result sets.
- [ ] **Test against a staging environment.** Run your integration tests against v2 before deploying to production.
- [ ] **Migrate existing data.** Run a one-off script to ensure all v1 tasks have a `project_id` assigned, and that any integer IDs stored externally are mapped to v2 UUIDs.

---

## Upgrade

Install the v2 CLI:

```bash
pip install --upgrade zrb
```

Verify the version:

```bash
zrb --version
# zrb 2.0.0
```

Once installed, all `zrb` commands target v2. Update your scripts as described above.
