# Zrb CLI v2 Migration Guide

This guide is designed for experienced developers who are currently using Zrb CLI v1. It details the breaking changes introduced in v2, provides before-and-after code examples, and offers a step-by-step checklist to ensure a smooth transition.

---

## Overview of Zrb v2

Version 2 (v2) of the Zrb CLI introduces several major improvements, including native project support, unified versioned routing, robust UUID identifiers, and standard Bearer-based authentication. While these changes make the platform more secure and scalable, they introduce breaking changes from v1.

---

## Breaking Changes

### 1. Unified Version Prefixing and Task Creation Requirements

In the new `/v2` API, creating a task requires a valid `project_id` in the request body. All task-related endpoints are now version-prefixed, meaning the v1 base paths no longer resolve.

#### Before (v1)
In v1, tasks were created under the bare `/tasks` endpoint, and they did not belong to any specific project.

```http
POST /tasks HTTP/1.1
Host: api.zrb.com
X-Auth-Token: your_v1_api_key
Content-Type: application/json

{
  "title": "Build migration guide"
}
```

#### After (v2)
In v2, all requests must be prefixed with `/v2/` (e.g., `/v2/tasks`). In addition, you must supply a `project_id`.

```http
POST /v2/tasks HTTP/1.1
Host: api.zrb.com
Authorization: Bearer your_v2_api_token
Content-Type: application/json

{
  "title": "Build migration guide",
  "project_id": "proj_abc123"
}
```

---

### 2. Authentication Header Update

We updated authentication to require the standard `Authorization` header with a `Bearer` token. The custom `X-Auth-Token` header used in v1 is fully deprecated and will now return an HTTP 401 Unauthorized status.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.com
X-Auth-Token: your_v1_api_key
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.com
Authorization: Bearer your_v2_api_token
```

---

### 3. Task ID Format Change

The task identifier `id` field was changed from a sequential integer to a standard `UUID` string. This prevents ID enumeration and ensures globally unique resource identification across multiple projects.

#### Before (v1)
The task ID was a plain integer:
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2)
The task ID is now a 36-character UUID string:
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

### 4. Task Completion Field Rename

The task status field has been renamed from `done` to `completed` in the v2 response structure. Any front-end or service code parsing the old `done` field must be updated.

#### Before (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2)
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": true,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 5. Paginated List Response Envelope

In v1, retrieving a list of tasks returned a bare JSON array. In v2, listing tasks returns a paginated response envelope containing an `items` array, a `total` count, and a `next_cursor` token to fetch subsequent pages.

#### Before (v1)
```json
[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

#### After (v2)
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
  "total": 1,
  "next_cursor": null
}
```

To fetch the next page in v2, pass the cursor as a query parameter:
```http
GET /v2/tasks?cursor=cursor_xyz&limit=20 HTTP/1.1
Host: api.zrb.com
Authorization: Bearer your_v2_api_token
```

---

## Migration Checklist

To successfully transition your existing codebase from Zrb CLI v1 to v2, follow this step-by-step checklist:

- [ ] **Backup Configuration:** Save your existing v1 setup and configurations.
- [ ] **Upgrade the Zrb CLI:** Execute the upgrade command to install the latest v2 version.
- [ ] **Prefix API Paths:** Update all endpoint calls to include the `/v2/` prefix.
- [ ] **Update Authentication:** Migrate your API clients from `X-Auth-Token` to the standard `Authorization: Bearer <token>` format.
- [ ] **Handle UUID Identifiers:** Update databases, routing, and data contracts to expect UUID strings instead of integers for task IDs.
- [ ] **Rename Field References:** Replace any references to the `done` field with the new `completed` field name.
- [ ] **Incorporate `project_id`:** Ensure all task creation payloads (`POST /v2/tasks`) include a valid `project_id`.
- [ ] **Adapt List Parsing:** Update your frontend/client parsers to read from the `.items` envelope instead of assuming a bare array.
- [ ] **Implement Cursor-Based Pagination:** Transition from offset/limit pagination to cursor-based traversal using `next_cursor`.
- [ ] **Verify and Test:** Run your integration test suites to confirm that all services communicate correctly with the new v2 API.

---

## Upgrade Command

To upgrade your local installation of the Zrb CLI to the latest v2 release, choose the appropriate package manager command below.

### Using pip (Python)
To upgrade using the standard Python package manager:
```bash
pip install --upgrade zrb
```

Alternatively, to pin to v2 specifically:
```bash
pip install "zrb>=2.0.0"
```

### Using pipx
If you have Zrb CLI installed in an isolated environment:
```bash
pipx upgrade zrb
```

### Using Poetry
For project-specific dependency management:
```bash
poetry add zrb@latest
```
```bash
poetry update zrb
```
