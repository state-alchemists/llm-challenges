# Migrating from Zrb API v1 to v2

Zrb API v2 introduces projects, pagination, and stricter authentication. Every endpoint, auth scheme, and data type is affected — no v1 endpoint will continue working after upgrade. This guide walks through each breaking change with before/after examples and a concrete migration checklist.

---

## Breaking Changes at a Glance

| # | Area | v1 | v2 |
|---|------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication | `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |
| 3 | Task ID type | integer (`42`) | UUID string (`"a1b2...ef"`) |
| 4 | Completion field | `done` | `completed` |
| 5 | Task creation | title only | title + `project_id` (required) |
| 6 | List response | bare JSON array | paginated envelope (`items`, `total`, `next_cursor`) |
| 7 | Pagination | none | cursor-based (`?cursor=`, `?limit=`) |

---

## 1. Endpoint Prefix

### Change

All endpoints are now prefixed with `/v2/`. The old `/tasks` routes return `404`.

### Before (v1)

```
GET /tasks
POST /tasks
GET /tasks/42
PUT /tasks/42
DELETE /tasks/42
```

### After (v2)

```
GET /v2/tasks
POST /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

> Note that route parameters also change from integers to UUIDs — see §3 below.

---

## 2. Authentication

### Change

The auth header moves from a custom `X-Auth-Token` to the standard `Authorization: Bearer` scheme. v1-style requests receive `401 Unauthorized`.

### Before (v1)

```
X-Auth-Token: sk_live_abc123
```

### After (v2)

```
Authorization: Bearer zrb_live_abc123
```

Update every HTTP client, SDK wrapper, and `curl` one-liner in your codebase.

---

## 3. Task ID Type — Integer to UUID

### Change

Task `id` is now a UUID string instead of an auto-incrementing integer. All endpoints that reference a task by ID now expect a UUID.

### Before (v1)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Impact:** Any code that assumes numeric IDs — URL construction, local storage, sorting — must be updated to handle UUID strings.

---

## 4. Field Rename — `done` → `completed`

### Change

The task completion flag is renamed from `done` to `completed`. All existing v1 tasks are migrated with the new field name; there is no transitional period.

### Before (v1)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": true
}
```

### After (v2)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Affects:** deserialization, display logic, filtering, and the `PUT/PATCH` request body when toggling completion status.

**Update `PUT /v2/tasks/{id}` request body:**

Before:

```json
{
  "done": true
}
```

After:

```json
{
  "completed": true
}
```

---

## 5. Required `project_id` on Task Creation

### Change

`POST /v2/tasks` now requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`. The `id` is auto-generated as a UUID; `created_at` is still auto-assigned.

### Before (v1)

```json
POST /tasks
Content-Type: application/json

{
  "title": "New task"
}
```

### After (v2)

```json
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task",
  "project_id": "proj_abc123"
}
```

**Impact:** You must obtain or create a project before creating tasks. Add project management logic to your onboarding or provisioning flow.

---

## 6. Paginated List Response

### Change

List endpoints no longer return a bare JSON array. Every list response is wrapped in a paginated envelope with an optional cursor for forward pagination.

### Before (v1)

```
GET /tasks
```

```json
[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:30:00Z"
  },
  {
    "id": 2,
    "title": "Ship v1",
    "done": true,
    "created_at": "2024-01-15T10:31:00Z"
  }
]
```

### After (v2)

```
GET /v2/tasks?limit=20&cursor=cursor_xyz
```

```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_abc"
}
```

**Changes to handle:**
- Access items via `response.items` instead of iterating `response` directly.
- Read `next_cursor` to determine if more pages exist (non-null means there are more results).
- Pass `?cursor=<next_cursor>` to fetch each subsequent page.
- The `limit` parameter controls page size (default 20). This replaces any client-side limit you may have been applying.

---

## What Stays the Same

These parts of the API are **unchanged** in v2:

| Aspect | v1 | v2 |
|--------|----|----|
| `title` field | string | string |
| `created_at` field | ISO 8601 timestamp | ISO 8601 timestamp |
| `DELETE` response | 204 No Content | 204 No Content |
| `GET /tasks/{id}` not found | 404 | 404 |
| `POST` response status | 201 Created | 201 Created |
| `PUT` body semantics | all fields optional | all fields optional |

---

## Step-by-Step Migration Checklist

- [ ] **Generate new API tokens.** Replace every `X-Auth-Token` header with `Authorization: Bearer <v2_token>`. Old tokens will not work.
- [ ] **Update all base URLs.** Change every API client's base path to include the `/v2/` prefix.
- [ ] **Audit integer ID usage.** Find every place your code stores, displays, or compares task IDs — these must now handle UUID strings.
- [ ] **Rename `done` to `completed`** in all request bodies, response parsers, and UI components.
- [ ] **Provision projects.** If your integration doesn't have a project concept, add project creation before task creation. `POST /v2/tasks` will reject requests without `project_id`.
- [ ] **Rewrite list-response parsing.** Change array iteration to unwrap `response.items`. Add pagination logic: check `next_cursor`, pass it back as `?cursor=` for the next page.
- [ ] **Update documentation.** Refresh any internal API docs, Postman collections, and code comments that reference the v1 API.
- [ ] **Test in staging.** Run your full integration test suite against the v2 API before cutting over in production.

---

## Upgrade Command

Deploy the v2 client library and run the migration script:

```bash
pip install zrb-client>=2.0.0
```

If you haven't already configured the new project and API token:

```bash
zrb login --token zrb_live_abc123
zrb project create --name "My Project"
```

Then run your migration tests:

```bash
python -m pytest tests/test_integration.py -v
```

Once green, update your staging and production environments. The v1 API will be decommissioned on **2026-07-01**.
