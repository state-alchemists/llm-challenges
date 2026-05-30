# Zrb Task API — v2 Migration Guide

This guide describes how to migrate your applications from Zrb Task API v1 to v2. 

v2 introduces support for projects, improved pagination, and stricter security protocols. While these additions offer greater architectural flexibility and performance, they introduce several breaking changes.

---

## Breaking Changes Reference

### 1. Base Endpoint URL Namespace Prefixing
All API endpoints are now nested under the `/v2/` URL namespace to facilitate concurrent version support and path modularity.

* **Before (v1):** `/tasks`, `/tasks/{id}`
* **After (v2):** `/v2/tasks`, `/v2/tasks/{id}`

#### Example Request Comparison

**Before (v1):**
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
```

**After (v2):**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
```

---

### 2. Authorization Header Format
The custom security header `X-Auth-Token` has been deprecated and replaced by standard Bearer token authorization using the standard `Authorization` header. Requests utilizing the old header structure will be rejected with an `HTTP 401 Unauthorized` response.

* **Before (v1):** `X-Auth-Token: <your_api_key>`
* **After (v2):** `Authorization: Bearer <your_api_token>`

#### Example Request Comparison

**Before (v1):**
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: my_secret_token_123
```

**After (v2):**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer my_secret_token_123
```

---

### 3. Task ID Schema (Integer to UUID)
Task identifiers are no longer sequential integers. To prevent ID collision in multi-project and distributed architectures, the `id` field has been migrated to a standard UUID string. You must update your routing parameters, database tables, and model parsers.

* **Before (v1):** `id` is an `integer`
* **After (v2):** `id` is a `string` (UUID)

#### Example Response JSON Comparison

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

---

### 4. Renamed Task State Field (`done` to `completed`)
To ensure semantically consistent field nomenclature across the platform, the task state field `done` is now renamed to `completed`. This affects all JSON request and response models, specifically including task queries, task creation responses, and updates via `PUT`.

* **Before (v1):** `"done": true`
* **After (v2):** `"completed": true`

#### Example Update Payload Comparison (`PUT`)

**Before (v1):**
```http
PUT /tasks/42 HTTP/1.1
Content-Type: application/json

{
  "title": "Updated title",
  "done": true
}
```

**After (v2):**
```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Content-Type: application/json

{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Mandatory `project_id` Field for Task Creation
With the introduction of multi-project isolation, all tasks must be assigned to a project. The request payload for creating tasks (`POST /v2/tasks`) now requires a non-empty `project_id`. Omitting this field will result in an `HTTP 422 Unprocessable Entity` error.

* **Before (v1):** Only `title` is required to create a task.
* **After (v2):** Both `title` and `project_id` are required to create a task.

#### Example Creation Payload Comparison (`POST`)

**Before (v1):**
```http
POST /tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2):**
```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Response Envelope
List endpoints (`GET /v2/tasks`) no longer return bare JSON arrays. To support cursor-based pagination and scalable list queries, v2 wraps the response items inside a metadata envelope containing total count and next page cursors.

* **Before (v1):** Returns `[...]` (Bare Array)
* **After (v2):** Returns `{"items": [...], "total": 123, "next_cursor": "..."}`

#### Example List Response Comparison (`GET`)

**Before (v1):**
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
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

**After (v2):**
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "f8e7d6c5-b4a3-2109-8765-43210fedcba9",
      "title": "Ship v1",
      "completed": true,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

---

## Step-by-Step Migration Checklist

Follow these steps in your application codebase to ensure a safe transition from v1 to v2:

- [ ] **Update Endpoint Prefixes:** Search your codebase for API calls targeting `/tasks` and rewrite them to target `/v2/tasks`.
- [ ] **Update Auth Headers:** Replace the custom header key `X-Auth-Token` with the standard header `Authorization: Bearer <your_api_token>`.
- [ ] **Adjust Identifier Types:** Update local models, schema definitions, and databases to treat task `id`s as UUID strings rather than auto-incrementing integers.
- [ ] **Map Field Names:** Rename task status properties in serialization and deserialization layers from `done` to `completed`.
- [ ] **Verify Creation Requests:** Ensure every `POST /v2/tasks` request body provides a non-null `project_id`.
- [ ] **Refactor List Parsing Logic:** Modify list handling logic from direct array parsing to unpacking the paginated payload envelope (`response.items`). Implement cursoring using `?cursor=` where applicable.

---

## Upgrading the Zrb CLI

To upgrade your local CLI tooling to support the latest v2 specifications, execute the following command:

```bash
pip install --upgrade zrb
```

Verify your installation has successfully updated:

```bash
zrb version
```
