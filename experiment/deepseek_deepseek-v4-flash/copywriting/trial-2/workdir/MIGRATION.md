# Migrating from Zrb API v1 to v2

v2 introduces **projects**, **cursor-based pagination**, and **stricter authentication**. Every existing client needs updates — there is no backward-compatibility layer. This guide covers every breaking change with before/after examples so you can migrate with confidence.

---

## Breaking Changes

### 1. Endpoint Prefix: `/tasks` → `/v2/tasks`

All endpoints are now mounted under `/v2/`. Requests to the old paths return HTTP 404.

**Before (v1)**

```bash
curl https://api.zrb.dev/tasks
```

```bash
curl https://api.zrb.dev/tasks/42
```

**After (v2)**

```bash
curl https://api.zrb.dev/v2/tasks
```

```bash
curl https://api.zrb.dev/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Also update any hardcoded base URLs in SDK configs, HTTP client wrappers, and documentation scripts.

---

### 2. Authentication: `X-Auth-Token` → `Authorization: Bearer`

The API key header has been replaced by a Bearer token. `X-Auth-Token` is no longer recognised and returns HTTP 401.

**Before (v1)**

```
X-Auth-Token: sk-abc123
```

**After (v2)**

```
Authorization: Bearer zp_a1b2c3d4e5f6
```

Update every HTTP client — API key rotation scripts, CI/CD pipelines, and local dev tooling.

---

### 3. Task ID: integer → UUID string

Task IDs are now UUID v4 strings instead of auto-incrementing integers. Existing integer IDs have been mapped to stable UUIDs — fetch the mapping from `/v2/id-migration` if you need to reconcile stored references.

**Before (v1)**

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2)**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Impact on call sites:

| Before | After |
|---|---|
| `GET /tasks/42` | `GET /v2/tasks/a1b2c3d4-...` |
| `PUT /tasks/42` | `PUT /v2/tasks/a1b2c3d4-...` |
| `DELETE /tasks/42` | `DELETE /v2/tasks/a1b2c3d4-...` |
| Integer comparisons and sorting | String equality and lexical/date-based ordering |

Any code that does arithmetic on task IDs (`id + 1`, `id % N`) must be rewritten since UUIDs are not sequential.

---

### 4. Field Rename: `done` → `completed`

The task completion flag is now named `completed`. The old field `done` will not appear in v2 responses, and sending `done` in a request body has no effect.

**Create / Update request (v1)**

```json
{
  "title": "Write tests",
  "done": true
}
```

**Create / Update request (v2)**

```json
{
  "title": "Write tests",
  "completed": true
}
```

**Response parsing (v1)**

```javascript
const task = await response.json();
console.log(task.done); // true
```

**Response parsing (v2)**

```javascript
const task = await response.json();
console.log(task.completed); // true
```

Search your codebase for `.done` and `["done"]` references on task objects — these must all migrate to `completed`.

---

### 5. `project_id` Is Now Required on Creation

Every task must belong to a project. The `project_id` field is required when creating a task. Omitting it returns HTTP 422.

**Before (v1)** — title only

```bash
curl -X POST https://api.zrb.dev/tasks \
  -H "X-Auth-Token: sk-abc123" \
  -H "Content-Type: application/json" \
  -d '{"title": "Write tests"}'
```

**After (v2)**

```bash
curl -X POST https://api.zrb.dev/v2/tasks \
  -H "Authorization: Bearer zp_a1b2c3d4e5f6" \
  -H "Content-Type: application/json" \
  -d '{"title": "Write tests", "project_id": "proj_abc123"}'

If your workflow creates tasks without a project context, you must first list or create a project:

```bash
# List existing projects
curl https://api.zrb.dev/v2/projects \
  -H "Authorization: Bearer zp_a1b2c3d4e5f6"

# Create a new project
curl -X POST https://api.zrb.dev/v2/projects \
  -H "Authorization: Bearer zp_a1b2c3d4e5f6" \
  -H "Content-Type: application/json" \
  -d '{"name": "Default"}'
```

---

### 6. List Responses: Bare Array → Paginated Envelope

List endpoints no longer return a bare array. They return an envelope with `items`, `total`, and `next_cursor` for cursor-based pagination.

**Before (v1)** — `GET /tasks`

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2)** — `GET /v2/tasks`

```json
{
  "items": [
    {"id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "e5f6a7b8-...", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": null
}
```

**Client update (v1)**

```javascript
const tasks = await response.json();
tasks.forEach(t => console.log(t.title));
```

**Client update (v2)**

```javascript
const data = await response.json();
data.items.forEach(t => console.log(t.title));
```

**Pagination (v1)** — no pagination or manual `?offset=&limit=` hack

**Pagination (v2)**

```javascript
let cursor = null;
do {
  const params = new URLSearchParams({ limit: 20 });
  if (cursor) params.set("cursor", cursor);

  const res = await fetch(`https://api.zrb.dev/v2/tasks?${params}`, {
    headers: { Authorization: "Bearer zp_a1b2c3d4e5f6" }
  });
  const page = await res.json();
  page.items.forEach(t => process(t));
  cursor = page.next_cursor;
} while (cursor);
```

---

## Migration Checklist

Use this checklist to track your migration progress. Each item maps to one breaking change above.

- [ ] **Prefix all endpoints with `/v2/`** — update every URL in your codebase (List, Get, Create, Update, Delete).
- [ ] **Replace `X-Auth-Token` with `Authorization: Bearer`** — generate new tokens and update every HTTP client.
- [ ] **Migrate task IDs from integers to UUIDs** — fetch the ID mapping from `/v2/id-migration` and update all stored references, foreign keys, and cache keys.
- [ ] **Rename `done` to `completed`** — update all request bodies, response parsers, UI bindings, and database column references.
- [ ] **Add `project_id` to task creation calls** — create or select a project for every ungrouped task.
- [ ] **Update list-response consumers to read `.items`** — any code that iterates the raw response array must now read `.items` from the envelope.
- [ ] **Adopt cursor-based pagination** — replace offset/limit hacks with `cursor` and `limit` query parameters.

## Upgrade

```bash
# Install the latest v2 CLI
npm install -g @zrb/cli@latest

# Or via Homebrew
brew upgrade zrb
```

Once installed, authenticate with your new token:

```bash
zrb login --token zp_a1b2c3d4e5f6
```

Run `zrb --version` to confirm you are on v2:

```bash
zrb --version
# Zrb CLI v2.0.0
```
