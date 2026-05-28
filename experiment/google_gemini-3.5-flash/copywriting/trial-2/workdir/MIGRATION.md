# Zrb Task API — v1 to v2 Migration Guide

This guide is designed to help developers migrate their applications from the Zrb Task API v1 to the new v2. v2 introduces support for projects, improved pagination, and stricter authentication mechanisms. 

---

## Overview of Breaking Changes

The transition to v2 includes six primary breaking changes:

1. **Endpoint Prefix**: All endpoints are now prefixed with `/v2/`.
2. **Authentication Header**: Changed from custom header `X-Auth-Token` to standard Bearer token.
3. **Task ID Type**: Changed from auto-assigned integers to UUID strings.
4. **Task Boolean Field Renamed**: `done` is now `completed`.
5. **Required project_id**: Creating a task now requires specifying a `project_id`.
6. **List Pagination**: The list tasks endpoint now returns a paginated envelope object instead of a bare JSON array.

---

## Detailed Breaking Changes & Migration Steps

### 1. Endpoint Prefix Change

To keep the API versioned and clean, all task endpoints have been prefixed with `/v2/`.

#### Before (v1)
```http
GET /tasks
GET /tasks/42
POST /tasks
PUT /tasks/42
DELETE /tasks/42
```

#### After (v2)
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authentication Header Change

Authentication has been upgraded from a custom token header to the industry-standard Bearer authentication pattern. In v2, passing the legacy `X-Auth-Token` header will result in an **HTTP 401 Unauthorized** response.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key_here
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token_here
```

---

### 3. Task ID Type Change (`integer` ➔ `UUID`)

Task IDs are no longer sequential integers. They are now standard UUID strings. If your database schemas, local states, or client models store task IDs as integers, you must update their types to accept strings / UUIDs.

#### Before (v1)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2)
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

### 4. Task Field Renamed (`done` ➔ `completed`)

The boolean field representing the task completion state has been renamed from `done` to `completed` to match industry naming conventions.

#### Before (v1)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Task Creation Requires `project_id`

In v2, all tasks must belong to a project. The request body for `POST /v2/tasks` must include a valid `project_id`. Omitting `project_id` will trigger an **HTTP 422 Unprocessable Entity** error.

#### Before (v1)
```json
{
  "title": "New task title"
}
```

#### After (v2)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Response Structure & Pagination

To improve performance, the `GET /v2/tasks` endpoint no longer returns a bare JSON array. It returns a paginated JSON envelope. You can pass an optional `limit` parameter (default 20) and `cursor` parameter to navigate pages.

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
  "next_cursor": "cursor_xyz"
}
```

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your codebases and integrations:

- [ ] **Update Endpoint URIs**: Prepend `/v2/` to all API client request configurations.
- [ ] **Refactor Authentication Headers**: Update your HTTP client configuration to use the `Authorization: Bearer <your_api_token>` header instead of `X-Auth-Token`.
- [ ] **Adjust Identifier Types**: Convert storage schemas, database columns, and client models storing task IDs from `integer` to `string` or `UUID`.
- [ ] **Rename Status Field**: Replace occurrences of the `done` property with `completed` in both incoming/outgoing payloads and data models.
- [ ] **Support Project Associations**: Ensure task creation forms, services, and scripts pass a valid `project_id` parameter when sending `POST /v2/tasks`.
- [ ] **Implement Paginated Parsing**: Modify client code parsing responses from list tasks to extract the tasks list from the `items` key of the envelope. Implement cursor-based pagination utilizing `next_cursor` and the `cursor` query parameter.

---

## Upgrade Command

To update the Zrb CLI to the latest v2 release, run:

```bash
pip install --upgrade zrb
```
