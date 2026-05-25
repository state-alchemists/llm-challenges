# Zrb CLI v1 → v2 Migration Guide

If you are using the Zrb Task API v1, this guide covers every breaking change in v2, with before/after examples and a checklist to get your code working against the new API. Read each section, apply the change, then run through the checklist at the end.

---

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | All endpoints prefixed with `/v2/` | Every URL changes |
| 2 | Auth header: `X-Auth-Token` → `Authorization: Bearer` | All client auth configs must update |
| 3 | Task `id`: integer → UUID string | All stored/retrieved IDs change type |
| 4 | Field `done` renamed to `completed` | Reads and writes must use the new name |
| 5 | `project_id` required on create | Task creation without it returns 422 |
| 6 | List response: bare array → paginated envelope | Parse `items` instead of top-level array |
| 7 | List supports `cursor` & `limit` query params | Pagination is now explicit |

---

## 1. URL Prefix: `/v2/`

**What changed.** All endpoints are now under `/v2/`. Requests to bare `/tasks` will fail.

**Before (v1):**

```http
GET /tasks
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2):**

```http
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

**Action:** Update your base URL or path prefix from `/` to `/v2/`.

---

## 2. Authentication Header

**What changed.** v1 used a custom header `X-Auth-Token`. v2 uses the standard `Authorization: Bearer` scheme. Requests with `X-Auth-Token` receive HTTP 401.

**Before (v1):**

```http
X-Auth-Token: sk_live_abc123
```

**After (v2):**

```http
Authorization: Bearer sk_live_abc123
```

**Action:** Replace the header name and scheme in every client. If your SDK abstracts auth, update the config property; if you construct headers manually, change the header string.

---

## 3. Task `id`: Integer → UUID String

**What changed.** Task identifiers are now UUID v4 strings instead of auto-incrementing integers. Tasks created in v1 and v2 use incompatible ID spaces.

**Before (v1):**

```json
GET /tasks/42
# Response:
{"id": 42, "title": "Write tests", "done": false}
```

**After (v2):**

```json
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
# Response:
{"id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false}
```

**Action:**
- Update any type annotation, database column, or variable that assumed `int` — it is now `str`.
- v1 integer IDs **will not** work as v2 UUIDs. If you reference tasks by hard-coded IDs, you must re-resolve them.
- Any client-side URL construction (e.g., `/tasks/${id}`) must now pass UUIDs.

---

## 4. Field `done` → `completed`

**What changed.** The boolean field that marks a task as finished is renamed from `done` to `completed`. The semantics are identical.

**Before (v1):**

```json
# Response:
{"id": 42, "title": "Ship v1", "done": true}

# Update request:
{"title": "Ship v1", "done": true}
```

**After (v2):**

```json
# Response:
{"id": "uuid...", "title": "Ship v1", "completed": true}

# Update request:
{"title": "Ship v1", "completed": true}
```

**Action:** Rename every `done` reference to `completed` in your code — response parsing, request construction, and any derived state.

---

## 5. `project_id` Required on Create

**What changed.** v1 accepted `POST /tasks` with only a `title`. v2 requires `project_id` in the request body. Omitting it returns HTTP 422 Unprocessable Entity.

**Before (v1):**

```http
POST /tasks
Content-Type: application/json

{"title": "New task"}

# Response: 201
{"id": 42, "title": "New task", "done": false}
```

**After (v2):**

```http
POST /v2/tasks
Content-Type: application/json

{"title": "New task", "project_id": "proj_abc123"}

# Response: 201
{"id": "uuid...", "title": "New task", "completed": false, "project_id": "proj_abc123"}
```

**Action:** Add `project_id` to every create call. Obtain valid project IDs from the `GET /v2/projects` endpoint (documented separately).

---

## 6. List Response: Paginated Envelope

**What changed.** v1 returned a bare JSON array. v2 wraps the array in an envelope with `items`, `total`, and `next_cursor`.

**Before (v1):**

```json
GET /tasks

[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**After (v2):**

```json
GET /v2/tasks?limit=20

{
  "items": [
    {"id": "uuid...", "title": "Buy milk", "completed": false}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Action:** Replace array-iteration logic with `response.items`. Use `response.total` for display counts. Check `next_cursor` to determine if more pages exist.

---

## 7. Pagination: Cursor-Based

**What changed.** v1 had no pagination. v2 defaults to 20 items per page and supports `cursor` and `limit` query parameters for explicit pagination.

**Before (v1):**

```javascript
const tasks = await fetch("/tasks").then(r => r.json());
// tasks is the full array
```

**After (v2):**

```javascript
async function fetchAllTasks() {
  let cursor = null;
  let all = [];
  do {
    const params = new URLSearchParams({limit: "100"});
    if (cursor) params.set("cursor", cursor);
    const res = await fetch(`/v2/tasks?${params}`).then(r => r.json());
    all.push(...res.items);
    cursor = res.next_cursor;
  } while (cursor);
  return all;
}
```

**Action:** Implement cursor-based pagination. Treat a falsy `next_cursor` as the terminal page.

---

## Migration Checklist

Go through each item and verify before deploying against v2:

- [ ] **URL prefix** — all requests use `/v2/` paths
- [ ] **Auth header** — `X-Auth-Token` replaced with `Authorization: Bearer`; old header is rejected
- [ ] **ID type** — all task `id` values treated as strings, not integers
- [ ] **Field rename** — every `done` read/write changed to `completed`
- [ ] **Task creation** — every `POST /v2/tasks` includes `project_id`
- [ ] **List parsing** — code reads `response.items` instead of the top-level array
- [ ] **Pagination** — list calls pass `cursor`/`limit` and handle `next_cursor` for multi-page fetches
- [ ] **Hard-coded IDs** — any integer task IDs (e.g., `42`) replaced with their UUID equivalents or re-fetched
- [ ] **Error handling** — tests cover the new 401 (bad auth) and 422 (missing `project_id`) responses

---

## Upgrade Zrb CLI

```bash
pip install --upgrade zrb
zrb --version
```

Confirm the version shows `v2.x.x`, then run the checklist above against your integration tests. The v1 API will remain available at `/tasks` for a deprecation window — but new features and fixes ship on v2 only.
