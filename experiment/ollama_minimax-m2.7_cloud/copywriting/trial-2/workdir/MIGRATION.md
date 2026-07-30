# Zrb CLI Migration Guide: v1 to v2

This guide covers every breaking change between Zrb CLI v1 and v2, with before/after examples and a step-by-step checklist to migrate your integration.

---

## Breaking Changes at a Glance

| # | Change | v1 | v2 |
|---|--------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication header | `X-Auth-Token` | `Authorization: Bearer <token>` |
| 3 | Task `id` type | Integer | UUID string |
| 4 | Task status field | `done` | `completed` |
| 5 | Task creation requirement | `title` only | `title` + `project_id` |
| 6 | List response format | Bare array | Paginated envelope |

---

## 1. Endpoint Prefix

All endpoints are now prefixed with `/v2/`.

**Before (v1)**
```
GET /tasks
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**After (v2)**
```
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

## 2. Authentication Header

The authentication header has changed from a custom header to a standard Bearer token.

**Before (v1)**
```http
X-Auth-Token: your_api_key_here
```

**After (v2)**
```http
Authorization: Bearer your_api_token_here
```

Requests using `X-Auth-Token` will receive `401 Unauthorized`.

---

## 3. Task `id` Type

Task IDs are now UUID strings instead of integers. Update any code that parses or stores task IDs.

**Before (v1)**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

**Migration action:** Ensure your ID handling code treats IDs as strings and can accommodate UUID formats.

---

## 4. Task Status Field Renamed

The `done` boolean field has been renamed to `completed`.

**Before (v1)**
```json
{ "id": 1, "title": "Ship v1", "done": true }
```

**After (v2)**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Ship v2", "completed": true }
```

**Migration action:** Rename all references from `done` to `completed` in your request bodies and response handling.

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before (v1)**
```http
POST /tasks
Content-Type: application/json

{ "title": "New task title" }
```

**After (v2)**
```http
POST /v2/tasks
Content-Type: application/json

{ "title": "New task title", "project_id": "proj_abc123" }
```

**Migration action:** Identify which project ID to associate with each task in your workflow. Pass `project_id` in every task creation request.

---

## 6. List Response Format

List endpoints now return a paginated envelope instead of a bare array.

**Before (v1)**
```json
[
  { "id": 1, "title": "Buy milk", "done": false, "created_at": "..." },
  { "id": 2, "title": "Ship v1", "done": true, "created_at": "..." }
]
```

**After (v2)**
```json
{
  "items": [
    { "id": "a1b2c3d4-...", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..." },
    { "id": "e5f6g7h8-...", "title": "Ship v2", "completed": true, "project_id": "proj_abc123", "created_at": "..." }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

**Pagination usage:** To fetch the next page, pass the `next_cursor` value as a query parameter:

```
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

The `limit` parameter defaults to 20 if omitted.

**Migration action:** Update response handling to read `response.items` instead of treating the response as a direct array. Implement cursor-based pagination if you support fetching beyond the first page.

---

## Step-by-Step Migration Checklist

- [ ] **Update base URL** — Change all endpoint paths from `/tasks` to `/v2/tasks`
- [ ] **Update auth header** — Replace `X-Auth-Token` with `Authorization: Bearer <token>`
- [ ] **Update ID handling** — Change task ID variables from integer to string type; accommodate UUID format
- [ ] **Rename `done` to `completed`** — Update all request/response code that reads or writes the status field
- [ ] **Add `project_id` to task creation** — Include `project_id` in every `POST /v2/tasks` body
- [ ] **Update list response parsing** — Change list response handling from direct array access to `response.items`
- [ ] **Handle pagination** — If your integration fetches multiple pages, implement cursor-based pagination using `next_cursor`
- [ ] **Test with a single resource first** — Verify auth and read operations before migrating write operations
- [ ] **Deploy and monitor** — Watch for `401` (bad auth), `404` (old URLs), and `422` (missing `project_id`) errors

---

## Upgrade Command

Once your integration is updated per the checklist above, install v2:

```bash
npm install -g zrb-cli@latest
```

Or, if you prefer a specific version:

```bash
npm install -g zrb-cli@2.0.0
```

Verify the upgrade:

```bash
zrb --version
```
