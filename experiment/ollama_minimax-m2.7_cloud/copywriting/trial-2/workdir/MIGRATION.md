# Zrb CLI Migration Guide: v1 → v2

This guide covers every breaking change when upgrading from Zrb CLI v1 to v2. Each section shows the v1 approach, the v2 replacement, and what you need to change.

## Breaking Changes at a Glance

| # | Change | Impact |
|---|--------|--------|
| 1 | Endpoint prefix `/v2/` | All URLs change |
| 2 | Auth header: `Bearer` token | Client code needs header rewrite |
| 3 | Task `id`: integer → UUID string | ID handling throughout |
| 4 | Field `done` → `completed` | All task payloads |
| 5 | `project_id` required on create | Creation calls |
| 6 | List returns envelope with pagination | Response parsing |

---

## 1. Endpoint Prefix

All endpoints now live under `/v2/`.

**v1**
```http
GET /tasks
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

**v2**
```http
GET /v2/tasks
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Update every URL in your client configuration and any hardcoded endpoint strings.

---

## 2. Authentication Header

The header key and format have both changed.

**v1**
```http
X-Auth-Token: <your_api_key>
```

**v2**
```http
Authorization: Bearer <your_api_token>
```

Requests that still send `X-Auth-Token` will receive `401 Unauthorized`. Migrate your auth header construction:

```javascript
// v1
headers: { 'X-Auth-Token': apiKey }

// v2
headers: { 'Authorization': `Bearer ${apiToken}` }
```

---

## 3. Task `id` Type: Integer → UUID

Task IDs are no longer integers. They are now UUID strings.

**v1 response**
```json
{ "id": 42, "title": "Write tests", "done": false }
```

**v2 response**
```json
{ "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "title": "Write tests", "completed": false }
```

Any code that treats `id` as a number—storing it as an integer, using string interpolation without quotes, or constructing URLs by concatenation—must be updated to handle UUID strings.

---

## 4. Field Renamed: `done` → `completed`

The task completion flag has been renamed.

**v1 task object**
```json
{ "id": 1, "title": "Ship v1", "done": true }
```

**v2 task object**
```json
{ "id": "a1b2c3d4-...", "title": "Ship v2", "completed": true }
```

Update every reference to `task.done` (or `task['done']`) to use `task.completed`.

---

## 5. Task Creation Requires `project_id`

Creating a task now requires a `project_id`. Sending a body without it returns `422 Unprocessable Entity`.

**v1**
```http
POST /tasks
{ "title": "New task" }
```

**v2**
```http
POST /v2/tasks
{ "title": "New task", "project_id": "proj_abc123" }
```

If you are pre-creating tasks without tracking which project they belong to, you will need to introduce project assignment into your workflow. Obtain a `project_id` from your project list endpoint (see v2 spec for new project endpoints).

---

## 6. List Response: Array → Paginated Envelope

List endpoints no longer return a bare array. They return a wrapper envelope.

**v1**
```json
[
  { "id": 1, "title": "Buy milk", "done": false },
  { "id": 2, "title": "Ship v1", "done": true }
]
```

**v2**
```json
{
  "items": [
    { "id": "...", "title": "Buy milk", "completed": false },
    { "id": "...", "title": "Ship v2", "completed": true }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

Update response handling to read `.items` for the array, and use `next_cursor` for pagination:

```javascript
// v1
const tasks = response.json();

// v2
const { items: tasks, total, next_cursor } = response.json();
if (next_cursor) fetchPage(next_cursor);
```

---

## Migration Checklist

Run through each item and mark it done. All items must be addressed.

- [ ] **Update all endpoint URLs** — add `/v2` prefix to every path
- [ ] **Replace auth header** — switch `X-Auth-Token` to `Authorization: Bearer <token>`
- [ ] **Update ID handling** — change any `parseInt(id)` calls; treat IDs as strings
- [ ] **Rename `done` field** — replace all `task.done` / `task['done']` with `task.completed`
- [ ] **Add `project_id` to create calls** — every `POST /v2/tasks` body needs it
- [ ] **Update list response parsing** — read `.items`, handle `.next_cursor` for pagination
- [ ] **Update any `id` in URLs** — UUID strings go directly into path segments
- [ ] **Check error handling** — `401` now means bad/missing Bearer token; `422` means missing `project_id`

---

## Upgrade Command

```bash
npm install zrb-cli@2
```

Or, if you prefer yarn:

```bash
yarn upgrade zrb-cli@2
```

After upgrading, test your integration against the v2 endpoints before deploying to production.
