# Zrb CLI v1 → v2 Migration Guide

v2 introduces projects, paginated list endpoints, stricter authentication, and several field and type changes. The v1 API continues to run at `/tasks` — but it is deprecated. Plan your migration before the v1 sunset.

## Breaking Changes at a Glance

| # | Area | v1 | v2 |
|---|------|----|----|
| 1 | Endpoint prefix | `/tasks` | `/v2/tasks` |
| 2 | Authentication | `X-Auth-Token: <key>` | `Authorization: Bearer <token>` |
| 3 | Task `id` type | Integer | UUID string |
| 4 | Task field `done` | `done` | `completed` |
| 5 | Create Task body | `{ title }` | `{ title, project_id }` |
| 6 | List response format | Bare array | Paginated envelope |

---

## 1. Endpoint Prefix

All endpoints now live under `/v2/`. Requests to `/tasks` return HTTP 404.

**v1**

```http
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

**v2**

```http
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

**Action:** Prepend `/v2` to every API path in your client configuration. Use a base URL constant rather than string-replacing each call.

---

## 2. Authentication

The auth mechanism has changed from a custom header to a standard Bearer token. v1-style `X-Auth-Token` requests receive HTTP 401.

**v1**

```http
X-Auth-Token: sk-abc123
```

**v2**

```http
Authorization: Bearer sk-abc123
```

**Action:** Replace the `X-Auth-Token` header with `Authorization: Bearer`. The token value itself may be the same credential — only the transport changed.

---

## 3. Task ID — Integer to UUID

The `id` field is now a UUID string. If your code stores, compares, or indexes task IDs as integers it will break.

**v1**

```json
{ "id": 42, "title": "Write tests", "done": false }
```

**v2**

```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

**Action:**
- Change ID columns/fields from integer to string (UUID v4).
- Remove integer auto-increment assumptions — IDs are now client-known or server-generated opaque strings.
- Update any URL construction that interpolates IDs: `/v2/tasks/${id}` (already a string — no `.toString()` needed).

---

## 4. Field Rename: `done` → `completed`

The boolean status field has been renamed. v2 ignores the old `done` key.

**v1 — reading a task**

```python
# Python
if task["done"]:
    print("Task is complete")
```

**v2 — reading a task**

```python
if task["completed"]:
    print("Task is complete")
```

**v1 — creating / updating a task**

```json
PUT /tasks/42
{ "done": true }
```

**v2 — creating / updating a task**

```json
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
{ "completed": true }
```

**Action:** Rename all `done` references in both read and write paths to `completed`.

---

## 5. Create Task — `project_id` Is Now Required

v1 allowed creating a task with only a `title`. v2 requires `project_id`.

**v1**

```http
POST /tasks

{ "title": "Fix login bug" }
```

**v2**

```http
POST /v2/tasks

{ "title": "Fix login bug", "project_id": "proj_abc123" }
```

Omitting `project_id` returns HTTP 422 with a validation error.

**Action:** Before creating any task, obtain or generate a `project_id`. If you don't yet have a project system, call `POST /v2/projects` to create one and retain its ID.

---

## 6. List Response — Bare Array to Paginated Envelope

List endpoints no longer return a flat JSON array. They return an envelope with pagination metadata.

**v1**

```http
GET /tasks

```
```json
[
  { "id": 1, "title": "Buy milk", "done": false },
  { "id": 2, "title": "Ship v1", "done": true }
]
```

**v2**

```http
GET /v2/tasks

```
```json
{
  "items": [
    { "id": "a1b2...", "title": "Buy milk", "completed": false },
    { "id": "c3d4...", "title": "Ship v1", "completed": true }
  ],
  "total": 2,
  "next_cursor": null
}
```

**v1 — iteration pattern**

```javascript
// JavaScript
const tasks = await fetch("/tasks").then(r => r.json());
tasks.forEach(t => console.log(t.title));
```

**v2 — iteration pattern**

```javascript
const { items, total, next_cursor } = await fetch("/v2/tasks").then(r => r.json());
console.log(`${items.length} of ${total} tasks`);
items.forEach(t => console.log(t.title));
```

**Action:**
- Unwrap the response: access `.items` instead of the root array.
- Use `.next_cursor` for pagination — pass it as `?cursor=` to fetch the next page.
- Default page size is 20; use `?limit=` to adjust.

---

## Migration Checklist

- [ ] **Update base URL** — change all API paths from `/tasks` to `/v2/tasks`.
- [ ] **Replace auth header** — `X-Auth-Token` → `Authorization: Bearer`.
- [ ] **Update ID types** — change task ID fields from integer to UUID string in your database schema, API models, and client code.
- [ ] **Rename `done` to `completed`** — update every read and write that references the task status field.
- [ ] **Add `project_id` to create requests** — obtain a project ID and include it in every `POST /v2/tasks` call.
- [ ] **Unwrap list responses** — access `.items` from the paginated envelope instead of treating the response as a bare array.
- [ ] **Handle pagination** — add logic for `?cursor=` parameter and the `next_cursor` field in responses.
- [ ] **Test against v2** — run your integration test suite against the `/v2/` endpoints before deploying.

---

## Upgrade

Install or update to the latest Zrb CLI:

```bash
pip install --upgrade zrb
```

Verify the API version:

```bash
zrb --version
```

API requests against the v2 endpoints should now respond as documented. If you hit issues, ensure all checklist items above are resolved.
