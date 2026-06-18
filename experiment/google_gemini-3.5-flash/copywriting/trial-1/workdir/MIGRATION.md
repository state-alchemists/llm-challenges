# Zrb CLI v2 Migration Guide

Welcome to the Zrb CLI v2 migration guide! This guide will walk you through transitioning your integration from the v1 API and CLI to the new Zrb v2 standard. Zrb v2 introduces support for projects, cleaner API paths, enhanced pagination capabilities, and stricter security protocols.

---

## High-Level Overview of Breaking Changes

Zrb v2 is a major release containing several backwards-incompatible changes. Before upgrading, please review the specific changes below to understand how they impact your existing codebase and applications.

Summary of key breaking changes:
1. All API endpoints are now prefixed with `/v2/` instead of raw paths.
2. Authentication has migrated to a standard Authorization Bearer header.
3. The Task `id` field datatype is now a UUID string instead of an integer.
4. The Task object's `done` boolean field has been renamed to `completed`.
5. Creating a new task now strictly requires a `project_id`.
6. Listing tasks returns a structured paginated envelope instead of a bare JSON array.

---

## Detailed Breaking Changes & Code Examples

Here is a detailed breakdown of each breaking change, along with before and after code examples.

### 1. New /v2 Endpoint Prefix and Required project_id for Task Creation

All endpoints in v2 are now prefixed with `/v2`, and creating a task now requires a `project_id` in the request body. If you omit the `project_id`, the API will reject the request with an HTTP 422 Unprocessable Entity error.

**Before (v1 API endpoint and request payload):**
```http
POST /tasks
X-Auth-Token: my-v1-secret-token
Content-Type: application/json

{
  "title": "Write unit tests"
}
```

**After (v2 API endpoint and request payload with /v2 prefix and project_id):**
```http
POST /v2/tasks
Authorization: Bearer my-v2-bearer-token
Content-Type: application/json

{
  "title": "Write unit tests",
  "project_id": "proj_abc123"
}
```

---

### 2. Authentication Header Migrated to Authorization Bearer

We are transitioning to standard HTTP Authorization headers using a Bearer token scheme.
The old custom `X-Auth-Token` header is deprecated. Any request sending `X-Auth-Token` will be rejected with an HTTP 401 Unauthorized status.

**Before (v1 Authentication):**
```http
GET /tasks
X-Auth-Token: your_api_key
```

**After (v2 Authentication: Authorization with Bearer token):**
```http
GET /v2/tasks
Authorization: Bearer your_api_token
```

---

### 3. Task ID Type Migrated from Integer to UUID

The task identifier `id` has transitioned from a sequential integer to a globally unique `uuid` string.
If your internal systems, database schemas, or API clients expect the `id` field to be an integer, you must update them to store and process UUID string representations.

**Before (v1 Task representation with integer id):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 Task representation with UUID string id):**
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

### 4. Task Field Renamed from done to completed

In Zrb v2, the `done` boolean field on the task object has been renamed to `completed`.
Ensure your database models, serializers, validation logic, and frontend components use the updated field name `completed` rather than `done`.

**Before (v1 done field):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false
}
```

**After (v2 completed field):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123"
}
```

---

### 5. Collection Endpoints Return Paginated Envelope instead of Bare Array

To improve performance and reliability for large collections, the Zrb v2 list endpoints now return a paginated envelope containing pagination metadata, rather than a raw, bare array. The new envelope wraps results in an `items` array and provides a `total` count along with a `next_cursor` string for cursor-based pagination.

**Before (v1 bare array response):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 paginated envelope response):**
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
  "next_cursor": "cursor_xyz"
}
```

To fetch subsequent pages, pass the `next_cursor` value to the `cursor` query parameter on `GET /v2/tasks`:
```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
Authorization: Bearer your_api_token
```

---

## Step-by-Step Migration Checklist

Follow this checklist to systematically migrate your systems and client integrations from Zrb v1 to v2:

- [ ] Update all API request paths to append the `/v2` prefix (e.g. change `/tasks` to `/v2/tasks`).
- [ ] Migrate your API request authentication headers to use `Authorization: Bearer <your_api_token>` instead of `X-Auth-Token`.
- [ ] Refactor your internal database schemas and serializers to parse the Task `id` as a UUID string rather than an integer.
- [ ] Rename the `done` boolean field reference on your models, API client payload structures, and frontend components to `completed`.
- [ ] Update your task creation logic to supply the required `project_id` field in the request payload body.
- [ ] Refactor your listing logic to parse paginated envelope structures (`items`, `total`, `next_cursor`) rather than a direct raw JSON array.
- [ ] Verify error-handling routines for HTTP 422 (for missing project_id) and HTTP 401 (for expired/missing bearer tokens).
- [ ] Upgrade the CLI and local SDK libraries to v2.

---

## Upgrading the Zrb CLI

Once your codebase changes are complete, upgrade your local Zrb CLI installation to v2.

To upgrade using pip:
```bash
pip install --upgrade zrb
```

To upgrade using pipx:
```bash
pipx upgrade zrb
```

To upgrade using poetry:
```bash
poetry add zrb@latest
```
