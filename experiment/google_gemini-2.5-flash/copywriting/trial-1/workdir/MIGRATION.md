# Zrb CLI v1 to v2 Migration Guide

This guide outlines the necessary steps and changes required to migrate your existing Zrb CLI v1 integrations to the new Zrb CLI v2 API. Version 2 introduces significant improvements, including project support, enhanced pagination, and stricter authentication, but also includes several breaking changes that you'll need to address.

Our goal is to make this transition as smooth as possible for experienced developers already familiar with v1.

## Table of Contents

1.  [Breaking Change: All Endpoints Now Prefixed with `/v2/`](#breaking-change-all-endpoints-now-prefixed-with-v2)
2.  [Breaking Change: Authentication Header Changed](#breaking-change-authentication-header-changed)
3.  [Breaking Change: Task `id` Type Changed](#breaking-change-task-id-type-changed)
4.  [Breaking Change: Task Field `done` Renamed to `completed`](#breaking-change-task-field-done-renamed-to-completed)
5.  [Breaking Change: Task Creation Now Requires `project_id`](#breaking-change-task-creation-now-requires-project_id)
6.  [Breaking Change: List Endpoints Return a Paginated Envelope](#breaking-change-list-endpoints-return-a-paginated-envelope)
7.  [Migration Checklist](#migration-checklist)
8.  [Upgrade Command](#upgrade-command)

---

## 1. Breaking Change: All Endpoints Now Prefixed with `/v2/`

All API endpoints in Zrb CLI v2 are now under the `/v2/` path prefix. This means that if you were previously making requests to `/tasks`, you will now need to prepend `/v2/` to the path.

### Before (v1)

```bash
curl -X GET 'https://api.zrb.com/tasks' \
  -H 'X-Auth-Token: <your_api_key>'
```

### After (v2)

```bash
curl -X GET 'https://api.zrb.com/v2/tasks' \
  -H 'Authorization: Bearer <your_api_token>'
```

## 2. Breaking Change: Authentication Header Changed

The authentication mechanism has been updated for improved security. The `X-Auth-Token` header is no longer supported. All requests must now use a Bearer token in the `Authorization` header.

Requests using the old `X-Auth-Token` will receive an HTTP 401 Unauthorized response.

### Before (v1)

```bash
curl ... \
  -H 'X-Auth-Token: <your_api_key>'
```

### After (v2)

```bash
curl ... \
  -H 'Authorization: Bearer <your_api_token>'
```

## 3. Breaking Change: Task `id` Type Changed

The `id` field for Task objects has changed from an integer to a UUID string. This affects all endpoints that reference tasks by their ID (Get, Update, Delete).

### Before (v1 Task Object)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2 Task Object)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Example (Get Task)

#### Before (v1)

```bash
curl -X GET 'https://api.zrb.com/tasks/42' \
  -H 'X-Auth-Token: <your_api_key>'
```

#### After (v2)

```bash
curl -X GET 'https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890' \
  -H 'Authorization: Bearer <your_api_token>'
```

## 4. Breaking Change: Task Field `done` Renamed to `completed`

The boolean field indicating a task's completion status has been renamed from `done` to `completed`. This change affects both the Task object structure and any requests that modify this status (e.g., Update Task).

### Before (v1 Task Object)

```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### After (v2 Task Object)

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Example (Update Task)

#### Before (v1)

```bash
curl -X PUT 'https://api.zrb.com/tasks/42' \
  -H 'X-Auth-Token: <your_api_key>' \
  -H 'Content-Type: application/json' \
  -d '{"done": true}'
```

#### After (v2)

```bash
curl -X PUT 'https://api.zrb.com/v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890' \
  -H 'Authorization: Bearer <your_api_token>' \
  -H 'Content-Type: application/json' \
  -d '{"completed": true}'
```

## 5. Breaking Change: Task Creation Now Requires `project_id`

To align with the new project-centric model, creating a new task (`POST /v2/tasks`) now requires a `project_id` in the request body. Omitting this field will result in an HTTP 422 Unprocessable Entity error.

### Before (v1 Create Task Request)

```json
{
  "title": "New task title"
}
```

### After (v2 Create Task Request)

```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### Example (Create Task)

#### Before (v1)

```bash
curl -X POST 'https://api.zrb.com/tasks' \
  -H 'X-Auth-Token: <your_api_key>' \
  -H 'Content-Type: application/json' \
  -d '{"title": "My new task"}'
```

#### After (v2)

```bash
curl -X POST 'https://api.zrb.com/v2/tasks' \
  -H 'Authorization: Bearer <your_api_token>' \
  -H 'Content-Type: application/json' \
  -d '{"title": "My new task", "project_id": "proj_abc123"}'
```

## 6. Breaking Change: List Endpoints Return a Paginated Envelope

List endpoints (e.g., `GET /v2/tasks`) no longer return a bare array of items. Instead, they return a paginated envelope object that includes the `items` array, `total` count, and a `next_cursor` for subsequent pages.

### Before (v1 List Tasks Response)

```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

### After (v2 List Tasks Response)

```json
{
  "items": [
    {"id": "uuid1", "title": "Buy milk", "completed": false, "project_id": "proj_abc123", "created_at": "..."},
    {"id": "uuid2", "title": "Ship v1", "completed": true, "project_id": "proj_abc123", "created_at": "..."}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

To retrieve the next page of results, pass the `next_cursor` as a query parameter: `?cursor=<next_cursor>`. You can also control the page size using the `limit` query parameter (default 20).

### Example (List Tasks)

#### Before (v1)

```bash
curl -X GET 'https://api.zrb.com/tasks' \
  -H 'X-Auth-Token: <your_api_key>'
```

#### After (v2)

```bash
# First page
curl -X GET 'https://api.zrb.com/v2/tasks?limit=10' \
  -H 'Authorization: Bearer <your_api_token>'

# Subsequent page
curl -X GET 'https://api.zrb.com/v2/tasks?cursor=cursor_xyz&limit=10' \
  -H 'Authorization: Bearer <your_api_token>'
```

## Migration Checklist

Use this checklist to ensure you've covered all necessary changes:

- [ ] **Update Endpoint Paths**: Prefix all Zrb API calls with `/v2/`.
- [ ] **Change Authentication Header**: Replace `X-Auth-Token` with `Authorization: Bearer <your_api_token>`.
- [ ] **Adjust Task ID Handling**: Update your code to expect and handle UUID strings for task IDs instead of integers.
- [ ] **Rename `done` to `completed`**: Update all references to the `done` field in Task objects and API requests to `completed`.
- [ ] **Add `project_id` to Task Creation**: Ensure all `POST /v2/tasks` requests include a valid `project_id` in the request body.
- [ ] **Refactor List Endpoint Responses**: Adapt your code to parse the new paginated envelope structure for list endpoints, accessing items via the `items` array and handling `next_cursor` for pagination.
- [ ] **Test All Integrations**: Thoroughly test all parts of your application that interact with the Zrb CLI to confirm the migration is complete and functional.

## Upgrade Command

Once you've made all the necessary code changes, upgrade your Zrb CLI installation to v2:

```bash
# Example for a hypothetical package manager (adjust for your actual setup)
npm install -g zrb-cli@latest
# or
pip install --upgrade zrb-cli
# or
brew upgrade zrb-cli
```

Confirm your Zrb CLI version after upgrade:

```bash
zrb --version
```

We hope this guide helps you successfully migrate to Zrb CLI v2. If you encounter any issues, please refer to the official Zrb v2 documentation or contact support.
