# Migrating from Zrb CLI v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. Every breaking change is documented below with before/after examples so you can upgrade with confidence.

---

## Breaking Changes

### 1. Endpoint Prefix — All Routes Now Under `/v2/`

Every endpoint has moved under the `/v2/` prefix. v1 paths respond with HTTP 404.

**v1**
```
GET /tasks
POST /tasks
GET /tasks/{id}
PUT /tasks/{id}
DELETE /tasks/{id}
```

**v2**
```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/{id}
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

### 2. Authentication Header — API Key Replaced by Bearer Token

The `X-Auth-Token` header is no longer accepted. Requests using it receive HTTP 401. All requests must now use the `Authorization` header with a Bearer token.

**v1**
```
X-Auth-Token: <your_api_key>
```

**v2**
```
Authorization: Bearer <your_api_token>
```

### 3. Task ID — Integer Changed to UUID String

The `id` field is now a UUID string. Any code that assumes an integer type — type assertions, arithmetic, or number-only validation — must be updated.

**v1**
```json
{
  "id": 42
}
```

**v2**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### 4. Task Status — `done` Renamed to `completed`

The `done` field no longer exists. Use `completed` everywhere — reading task status, creating tasks, and updating tasks.

**v1**
```json
{
  "done": false
}
```

**v2**
```json
{
  "completed": false
}
```

This affects both reads and writes:

**Creating a task**

| v1 | v2 |
|---|---|
| `POST /tasks` | `POST /v2/tasks` |
| `{"title": "Write tests"}` | `{"title": "Write tests", "completed": false}` |

**Updating a task**

| v1 | v2 |
|---|---|
| `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| `{"done": true}` | `{"completed": true}` |

### 5. Task Creation — `project_id` Is Now Required

Every new task must be scoped to a project. The `project_id` field is mandatory. Omitting it returns HTTP 422.

**v1** — only `title` needed
```json
POST /tasks
{
  "title": "Write tests"
}
```

**v2** — `project_id` now required
```json
POST /v2/tasks
{
  "title": "Write tests",
  "project_id": "proj_abc123"
}
```

### 6. List Response — Bare Array Replaced by Paginated Envelope

`GET /v2/tasks` no longer returns a bare array. Instead it returns an envelope with items, a total count, and a cursor for fetching the next page.

**v1**
```json
GET /tasks
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**v2**
```json
GET /v2/tasks
{
  "items": [
    {"id": "a1b2...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "c3d4...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

Access items via `response.items` instead of iterating the response directly. To fetch the next page, pass `?cursor=<next_cursor>`.

**Query parameters:**
| Parameter | Type | Default | Description |
|---|---|---|---|
| `cursor` | string | — | Cursor value from the previous response's `next_cursor` |
| `limit` | integer | 20 | Maximum items per page |

---

## Step-by-Step Migration Checklist

1. **Update API base URL** — Add `/v2` to the path of every endpoint call.
2. **Replace auth header** — Remove `X-Auth-Token`, add `Authorization: Bearer <token>`. Generate a new token if needed.
3. **Update ID handling** — Change all `int` types, assertions, and serialization for task IDs to expect UUID strings.
4. **Rename `done` to `completed`** — Update all read paths, create payloads, and update payloads.
5. **Add `project_id` to task creation** — Identify the project scope and include `project_id` in every `POST /v2/tasks` call. Pre-create projects via the new project endpoints if needed.
6. **Update list-consumption code** — Change bare-array iteration to read from `response.items`. Handle the `total` and `next_cursor` fields.
7. **Wire up pagination** — Where you iterate over all tasks, add cursor-based pagination via the `cursor` query parameter.
8. **Update error handling** — v1 HTTP 404 for missing resources may now arrive as HTTP 422 for validation errors (e.g., missing `project_id`). Audit your error-handling paths.

---

## Upgrade

Install the v2 CLI:

```
pip install --upgrade zrb
```

Verify the new version:

```
zrb --version
```

Test your first v2 call:

```
curl -H "Authorization: Bearer <your_api_token>" \
  https://api.zrb.dev/v2/tasks
```
