# Migrating to Zrb Task API v2

Zrb v2 ships a new Task API with six breaking changes. If you use v1 today, every one of them will affect your code, and v1 endpoints are **not** served side-by-side — un-migrated requests fail with `401`, `404`, or `422`.

This guide is for developers already working with v1. For each breaking change you get: what changed, why it matters, and a before/after example. A step-by-step checklist and the upgrade command are at the end.

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication | `X-Auth-Token` header | `Authorization: Bearer` header |
| 3 | Task `id` type | integer (e.g. `42`) | UUID string (e.g. `"a1b2c3d4-…"`) |
| 4 | Completion flag | `done` | `completed` |
| 5 | Task creation | `title` only | `title` + required `project_id` |
| 6 | List responses | bare array | paginated envelope |

---

## 1. Endpoints are now prefixed with `/v2/`

Every endpoint moved under `/v2/`. This applies to all five operations.

| Operation | v1 | v2 |
|-----------|----|----|
| List tasks | `GET /tasks` | `GET /v2/tasks` |
| Get task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create task | `POST /tasks` | `POST /v2/tasks` |
| Update task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

**Before (v1):**

```bash
curl https://api.zrb.dev/tasks \
  -H "X-Auth-Token: $ZRB_API_KEY"
```

**After (v2):**

```bash
curl https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer $ZRB_API_TOKEN"
```

In code, audit every URL builder and base-path constant. A single shared base URL is the safest change:

**Before (v1):**

```python
BASE_URL = "https://api.zrb.dev"
url = f"{BASE_URL}/tasks"
```

**After (v2):**

```python
BASE_URL = "https://api.zrb.dev/v2"
url = f"{BASE_URL}/tasks"
```

---

## 2. Authentication: `X-Auth-Token` → `Authorization: Bearer`

The API key header is gone. v2 requires a bearer token, and **any request sent with the v1 `X-Auth-Token` header is rejected with `HTTP 401`** — there is no fallback.

**Before (v1):**

```
X-Auth-Token: <your_api_key>
```

**After (v2):**

```
Authorization: Bearer <your_api_token>
```

**Before (v1):**

```bash
curl https://api.zrb.dev/tasks \
  -H "X-Auth-Token: $ZRB_API_KEY"
```

**After (v2):**

```bash
curl https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer $ZRB_API_TOKEN"
```

Update clients, SDK initializers, and CI secrets. In an SDK that maps config to headers:

**Before (v1):**

```python
client = ZrbClient(api_key=os.environ["ZRB_API_KEY"])
```

**After (v2):**

```python
client = ZrbClient(token=os.environ["ZRB_API_TOKEN"])
```

---

## 3. Task `id`: integer → UUID string

Task IDs are now UUID strings instead of auto-assigned integers.

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

This affects URLs, stored state, and any code that treats IDs as numbers:

**Before (v1):**

```bash
curl https://api.zrb.dev/tasks/42 \
  -H "X-Auth-Token: $ZRB_API_KEY"
```

**After (v2):**

```bash
curl https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer $ZRB_API_TOKEN"
```

Where this bites:

- **Type annotations** — `int` → `str` in models, ORMs, and cache keys.
- **Migrations** — persisted v1 integer IDs must be re-mapped to the new UUIDs (there is no integer→UUID derivation).
- **Comparisons** — code like `task["id"] == 42` or `int(task["id"])` breaks; treat IDs as opaque strings.
- **Ordering** — do not assume ID order is chronological; UUIDs are not auto-incrementing.

---

## 4. `done` renamed to `completed`

The completion flag is now `completed`. The rename applies everywhere the field appears: list, get, create, and update responses, and the update request body.

**Before (v1) — task object:**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2) — task object:**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

**Before (v1) — update request body:**

```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) — update request body:**

```json
{
  "title": "Updated title",
  "completed": true
}
```

Grep your codebase for `done` and rename the field in models, UI bindings, and tests. In a client model:

**Before (v1):**

```python
class Task:
    def __init__(self, id, title, done):
        self.id = id
        self.title = title
        self.done = done
```

**After (v2):**

```python
class Task:
    def __init__(self, id, title, completed, project_id):
        self.id = id
        self.title = title
        self.completed = completed
        self.project_id = project_id
```

---

## 5. Task creation now requires `project_id`

`POST /v2/tasks` requires `project_id`. Omitting it returns **`HTTP 422`** — the task is not created.

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

**Before (v1):**

```bash
curl https://api.zrb.dev/tasks \
  -X POST \
  -H "X-Auth-Token: $ZRB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title"}'
```

**After (v2):**

```bash
curl https://api.zrb.dev/v2/tasks \
  -X POST \
  -H "Authorization: Bearer $ZRB_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "New task title", "project_id": "proj_abc123"}'
```

Practical steps:

- Resolve the target project before creating tasks (e.g., from your deployment config or the project-management flow that provisions tasks).
- Add `422` to your error-handling path — it is a new failure mode you will hit in CI until every call site is updated.
- Update fixtures, seed scripts, and documentation examples that create tasks.

---

## 6. List endpoints return a paginated envelope

List responses are no longer a bare array. Every list endpoint returns an envelope, and pagination is cursor-based.

**Before (v1) — response:**

```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2) — response:**

```json
{
  "items": [
    { "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

The envelope fields:

- `items` — the page of task objects (was the whole array before).
- `total` — total number of tasks across all pages.
- `next_cursor` — pass this as `?cursor=<next_cursor>` to fetch the next page; absent/null means you are on the last page.

Two query parameters are available: `cursor` (pagination cursor, optional) and `limit` (max results per page, **default 20**). Code that assumed "the response is everything" must now loop.

**Before (v1):**

```python
tasks = client.get("/tasks")          # list of task objects
for task in tasks:
    print(task["title"])
```

**After (v2):**

```python
cursor = None
while True:
    page = client.get(
        "/v2/tasks",
        params={"cursor": cursor, "limit": 100},
    )
    for task in page["items"]:
        print(task["title"])
    cursor = page.get("next_cursor")
    if not cursor:
        break
```

Where this bites:

- Any code that indexes the response directly (`tasks[0]`, `len(tasks)`) must go through `items`.
- If you relied on getting all results in one request, the default `limit` of 20 silently truncates output — handle pagination explicitly.
- Deserialization into a typed array (e.g. `List[Task]` from JSON) must be pointed at `items`.

---

## What Has NOT Changed

To keep the diff focused, these behaviors are identical in v2:

- `title` and `created_at` fields, and the ISO 8601 timestamp format.
- Create still returns the created task object with `HTTP 201`.
- Update (`PUT`) still accepts partial bodies; all fields remain optional.
- Get on a missing task still returns `HTTP 404`; delete still returns `HTTP 204`.

---

## Migration Checklist

Work through these in order. Each step is independently verifiable.

- [ ] **1. Upgrade to v2.** Run the upgrade command at the bottom of this page.
- [ ] **2. Switch credentials.** Obtain a v2 API token; replace `X-Auth-Token`/`ZRB_API_KEY` with `Authorization: Bearer`/`ZRB_API_TOKEN` in code, config, and CI secrets.
- [ ] **3. Prefix URLs.** Update every endpoint to the `/v2/` base; search for `"/tasks"` across the codebase.
- [ ] **4. Treat IDs as strings.** Migrate stored integer IDs to the new UUIDs; update type annotations, cache keys, and any `int(id)` handling.
- [ ] **5. Rename `done` → `completed`.** Update models, response parsing, update payloads, UI bindings, and tests.
- [ ] **6. Provide `project_id` on create.** Resolve the project before creating tasks and update fixtures; add `422` to error handling.
- [ ] **7. Handle the paginated envelope.** Read `items`, use `total` for counts, and loop on `next_cursor`; set an explicit `limit` where the default 20 is too small.
- [ ] **8. Update error handling.** `401` (bad/old auth), `404` (missing task), `422` (validation), and `204` (delete) — make sure your client maps them all.
- [ ] **9. Update test fixtures and mocks.** Replace v1 arrays/IDs/fields with v2 shapes so CI exercises the real contract.
- [ ] **10. Smoke-test end to end.** Create → list (verify pagination with more than 20 tasks) → get → update → delete against `/v2/`.

## Upgrade Command

```bash
pip install --upgrade zrb
```

Verify the install with `zrb --version` (it should report v2), then confirm the API is reachable:

```bash
curl https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer $ZRB_API_TOKEN"
```
