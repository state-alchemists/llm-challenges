# Migrating from Zrb Task API v1 to v2

v2 introduces projects, cursor-based pagination, and stricter authentication. These improvements come with **six breaking changes** that require code updates before you can upgrade.

This guide walks through each breaking change with before/after examples, then closes with a migration checklist.

---

## Breaking Changes

### 1. All endpoints are now prefixed with `/v2/`

Every request URL must include the `/v2/` prefix. Requests to the old paths receive `404`.

**Before (v1):**

```python
response = requests.get("https://api.zrb.dev/tasks", headers=headers)
```

**After (v2):**

```python
response = requests.get("https://api.zrb.dev/v2/tasks", headers=headers)
```

**Scope:** `GET /tasks`, `GET /tasks/{id}`, `POST /tasks`, `PUT /tasks/{id}`, `DELETE /tasks/{id}` — all of them.

---

### 2. Authentication header changed from `X-Auth-Token` to Bearer token

The custom `X-Auth-Token` header is no longer accepted. Requests using it receive `401 Unauthorized`.

**Before (v1):**

```python
headers = {"X-Auth-Token": "sk_live_abc123"}
```

**After (v2):**

```python
headers = {"Authorization": "Bearer sk_live_abc123"}
```

---

### 3. Task `id` type changed from integer to UUID string

The `id` field on every task object is now a UUID string instead of an integer. Any code that parses, stores, or compares `id` as an integer must be updated.

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

If your database schema or models store `id` as an integer column, migrate it to a string/UUID column before pointing at v2.

---

### 4. Task field `done` renamed to `completed`

The boolean field `done` is now `completed`. Any code that reads or writes `done` must be updated.

**Before (v1):**

```python
# Create or update a task
payload = {"title": "Ship feature", "done": True}
```

**After (v2):**

```python
# Create or update a task
payload = {"title": "Ship feature", "completed": True}
```

Responses also use `completed` — update any deserialization or field mapping accordingly.

---

### 5. Task creation now requires `project_id`

`POST /v2/tasks` requires a `project_id` field. Omitting it returns `422 Unprocessable Entity`.

**Before (v1):**

```python
payload = {"title": "New task title"}
response = requests.post("https://api.zrb.dev/v2/tasks", json=payload, headers=headers)
```

**After (v2):**

```python
payload = {"title": "New task title", "project_id": "proj_abc123"}
response = requests.post("https://api.zrb.dev/v2/tasks", json=payload, headers=headers)
```

You will need to create or look up a project ID before creating tasks. Project management endpoints are new in v2 — see the v2 API reference for details.

---

### 6. List endpoints return a paginated envelope instead of a bare array

`GET /v2/tasks` no longer returns a bare JSON array. It returns an envelope with `items`, `total`, and `next_cursor`. Any code that iterates the top-level response as an array will break.

**Before (v1):**

```python
response = requests.get("https://api.zrb.dev/tasks", headers=headers)
tasks = response.json()  # direct list
for task in tasks:
    print(task["title"])
```

**After (v2):**

```python
response = requests.get("https://api.zrb.dev/v2/tasks", headers=headers)
data = response.json()        # envelope
for task in data["items"]:
    print(task["title"])

# Fetch next page
if data["next_cursor"]:
    requests.get(
        f"https://api.zrb.dev/v2/tasks?cursor={data['next_cursor']}",
        headers=headers,
    )
```

To fetch all tasks, loop until `next_cursor` is `null` or absent. You can also pass `?limit=N` to control page size (default 20).

---

## Migration Checklist

Work through these steps in order. Each corresponds to one of the breaking changes above.

- [ ] **Update all endpoint URLs** — add the `/v2/` prefix to every request path (`/tasks` → `/v2/tasks`).
- [ ] **Switch authentication headers** — replace `X-Auth-Token` with `Authorization: Bearer`. Remove any `X-Auth-Token` handling from your code.
- [ ] **Migrate `id` storage** — update database schemas, models, and type definitions from integer to UUID string. Run any schema migrations before deploying v2 integration.
- [ ] **Rename `done` → `completed`** — update all reads, writes, and field mappings in serialization code, templates, and tests.
- [ ] **Add `project_id` to task creation** — determine how your application will obtain or assign a project ID. Update every `POST /v2/tasks` call to include it.
- [ ] **Parse the paginated envelope** — replace direct-array iteration with `response["items"]`. Implement cursor-based pagination loops where you previously assumed a single response contained all results.

---

## Upgrade

```bash
npm install zrb@2
```