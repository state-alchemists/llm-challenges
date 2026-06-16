# Zrb CLI v2 Migration Guide

This guide is designed to help developers migrate their integrations, API clients, and codebases from the Zrb Task API v1 to v2. 

v2 introduces support for projects, improved pagination, and stricter authentication. Several existing v1 fields, data types, and API conventions have changed, which introduces breaking changes.

---

## Breaking Changes Summary

Here is a summary of the breaking changes when upgrading to v2:

1. **Endpoint Prefix**: All endpoints are now prefixed with `/v2/`.
2. **Authentication Header**: Changed from `X-Auth-Token` to `Authorization: Bearer`.
3. **Task ID Type**: Changed from `integer` to `UUID string`.
4. **Done Field Renamed**: Task field `done` is now renamed to `completed`.
5. **Required Project ID**: Task creation (`POST`) now requires a `project_id`.
6. **Paginated Response Envelope**: List endpoints return a paginated object instead of a bare JSON array.

---

## Detailed Changes & Code Examples

### 1. Endpoint Prefix Change

All API endpoints are now prefixed with `/v2/` to support versioning. Clients making requests to v1 paths (without the version prefix) must update their base URLs.

#### Endpoint Mapping

| Operation | v1 Path | v2 Path |
| :--- | :--- | :--- |
| List Tasks | `GET /tasks` | `GET /v2/tasks` |
| Get Task | `GET /tasks/{id}` | `GET /v2/tasks/{id}` |
| Create Task | `POST /tasks` | `POST /v2/tasks` |
| Update Task | `PUT /tasks/{id}` | `PUT /v2/tasks/{id}` |
| Delete Task | `DELETE /tasks/{id}` | `DELETE /v2/tasks/{id}` |

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.example.com
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.example.com
```

---

### 2. Authentication Header Change

The authentication header has been updated to follow standard OAuth2 Bearer token conventions. The custom header `X-Auth-Token` is deprecated; using it in v2 will result in an `HTTP 401 Unauthorized` response.

#### Before (v1)
```http
GET /tasks HTTP/1.1
X-Auth-Token: your_api_key_here
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer your_api_token_here
```

---

### 3. Task ID Data Type Change

Task identifiers (`id`) have been migrated from auto-incrementing integers to globally unique UUID strings. Any local data stores, client-side types, or routing code that expects integer IDs must be updated to support string-based UUIDs.

#### Before (v1 Task Schema)
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### After (v2 Task Schema)
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

### 4. Renamed Field: `done` to `completed`

The boolean property indicating a task's status has been renamed from `done` to `completed`. This affects task JSON responses, task creation, and task update requests.

#### Before (v1 Payload)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2 Payload)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Required `project_id` on Task Creation

v2 introduces scoped project task tracking. Creating a task via `POST /v2/tasks` now requires a `project_id` string in the request body. If `project_id` is omitted, the API will return `HTTP 422 Unprocessable Entity`.

#### Before (v1 Task Creation Request)
```http
POST /tasks HTTP/1.1
Content-Type: application/json
X-Auth-Token: your_api_key_here

{
  "title": "New task title"
}
```

#### After (v2 Task Creation Request)
```http
POST /v2/tasks HTTP/1.1
Content-Type: application/json
Authorization: Bearer your_api_token_here

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated List Response Envelope

The list tasks endpoint (`GET /v2/tasks`) no longer returns a bare JSON array of task objects. It now returns a paginated JSON envelope containing pagination metadata alongside the task items. Additionally, you can control pagination with the optional `cursor` and `limit` (default 20) query parameters.

#### Before (v1 Listing Response)
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
    "created_at": "2024-01-15T11:00:00Z"
  }
]
```

#### After (v2 Listing Response)
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

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your code integration from v1 to v2:

- [ ] **Step 1: Update API Endpoint Prefixes**
  - Locate all occurrences of API calls in your source code.
  - Prefix all paths with `/v2/` (e.g., change `/tasks` to `/v2/tasks`).
- [ ] **Step 2: Update Authentication Header**
  - Replace the header `X-Auth-Token: <your_api_key>` with standard `Authorization: Bearer <your_api_token>`.
- [ ] **Step 3: Modify Task Schema Types**
  - Update your task data models or type definitions.
  - Change the `id` field type from `number` / `integer` to `string` (UUID).
  - Rename the `done` boolean field to `completed`.
  - Add the `project_id` field (type `string`) as a required property.
- [ ] **Step 4: Update Task Creation Requests**
  - Verify that every `POST /v2/tasks` request payload includes a valid `project_id` key/value.
- [ ] **Step 5: Update Task Listing Logic**
  - Refactor your response-parsing logic for `GET /v2/tasks`.
  - Extract the tasks list from the nested `items` array property instead of reading the response root.
  - Implement cursor-based pagination handling if you traverse multiple pages, utilizing the `next_cursor` property and `?cursor=` query parameter.

---

## Upgrade Command

To upgrade the Zrb CLI to the latest v2 version, run the following command:

```bash
pip install --upgrade zrb
```

*If Zrb was installed globally via `pipx`, use:*

```bash
pipx upgrade zrb
```
