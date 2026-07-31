# Migrating to Zrb CLI v2

Zrb CLI v2 introduces significant architectural improvements, including project support, better pagination, and updated security standards. This guide will help you migrate your existing v1 integrations to the v2 API.

## Breaking Changes

### 1. API Versioning and Endpoints
All API endpoints are now versioned. You must prefix your requests with `/v2/`.

**v1:**
`GET /tasks`

**v2:**
`GET /v2/tasks`

### 2. Authentication Method
The authentication header has moved from a custom token header to the industry-standard Bearer token format.

**v1:**
```http
X-Auth-Token: <your_api_key>
```

**v2:**
```http
Authorization: Bearer <your_api_token>
```

### 3. Task ID Type Change
Task IDs have transitioned from integers to UUID strings to support better distributed scaling.

**v1:**
```json
{
  "id": 42,
  "title": "Write tests"
}
```

**v2:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. Task Completion Field
The field `done` has been renamed to `completed` for better clarity.

**v1:**
```json
{
  "done": true
}
```

**v2:**
```json
{
  "completed": true
}
```

### 5. Mandatory Project Association
Tasks can no longer exist globally. All new tasks must be associated with a `project_id`.

**v1:**
```json
{
  "title": "New task title"
}
```

**v2:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

### 6. Paginated List Responses
List endpoints no longer return a bare array. They now return a paginated envelope to ensure performance as your task lists grow.

**v1:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```

**v2:**
```json
{
  "items": [
    {"id": "uuid-1", "title": "Buy milk", "completed": false},
    {"id": "uuid-2", "title": "Ship v1", "completed": true}
  ],
  "total": 2,
  "next_cursor": "cursor_xyz"
}
```

## Migration Checklist

- [ ] Update all endpoint URLs to include the `/v2/` prefix.
- [ ] Update authentication headers from `X-Auth-Token` to `Authorization: Bearer`.
- [ ] Update data models to handle UUID strings instead of integers for Task IDs.
- [ ] Rename all occurrences of the `done` field to `completed`.
- [ ] Ensure all `POST /v2/tasks` requests include a valid `project_id`.
- [ ] Update list-handling logic to extract tasks from the `.items` array and implement cursor-based pagination.

## Upgrade Command

To update your CLI to the latest version, run:

```bash
zrb upgrade --to-v2
```
