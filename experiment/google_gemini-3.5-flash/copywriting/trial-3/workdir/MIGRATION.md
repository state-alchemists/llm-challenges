# Zrb Task API — v1 to v2 Migration Guide

This guide details the breaking changes introduced in Zrb Task API v2 and provides instructions for migrating your existing v1 integrations. 

v2 introduces support for projects, improved cursor-based pagination, and stricter authentication policies. All v1 endpoints are deprecated and will return `HTTP 410 Gone` once decommissioned.

---

## Summary of Breaking Changes

The v2 release includes six major breaking changes:
1. **Endpoint Prefixing**: All endpoints now require a `/v2/` path prefix.
2. **Authentication Header**: Changed from `X-Auth-Token` to a standard Bearer token (`Authorization` header).
3. **Task ID Format**: Changed from auto-assigned integers to UUID strings.
4. **Completion Field Renamed**: The `done` field is renamed to `completed`.
5. **Required Project Scope**: Task creation now requires a `project_id` field.
6. **Paginated Envelope**: List endpoints now return an object envelope rather than a bare array.

---

## Breaking Changes Deep Dive

### 1. API Endpoint Path Prefix
All routes have been updated to use the version namespace prefix `/v2/` (`v2_spec.md:9`). Requests to v1 endpoints without this prefix will fail.

#### Before (v1)
```http
GET /tasks
GET /tasks/{id}
POST /tasks
PUT /tasks/{id}
DELETE /tasks/{id}
```

#### After (v2)
```http
GET /v2/tasks
GET /v2/tasks/{id}
POST /v2/tasks
PUT /v2/tasks/{id}
DELETE /v2/tasks/{id}
```

---

### 2. Authentication Header Update
The legacy authentication header has been deprecated (`v1_spec.md:5-9`). v2 requires standard HTTP Bearer authorization (`v2_spec.md:18-27`). Any request passing the old `X-Auth-Token` header to a `/v2/` endpoint will receive an `HTTP 401 Unauthorized` response.

#### Before (v1)
```http
X-Auth-Token: <your_api_key>
```
Using `curl`:
```bash
curl -H "X-Auth-Token: your_api_key_here" https://api.zrb.dev/tasks
```

#### After (v2)
```http
Authorization: Bearer <your_api_token>
```
Using `curl`:
```bash
curl -H "Authorization: Bearer your_api_token_here" https://api.zrb.dev/v2/tasks
```

---

### 3. Task ID Data Type (Integer to UUID)
Task identifiers are now generated as globally unique UUID strings rather than auto-assigned integers (`v1_spec.md:17`, `v2_spec.md:34`). Update any client-side schema definitions, type casting, or database tables referencing the `id` field.

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

### 4. Field Rename: `done` to `completed`
To clarify execution state across complex task structures, the boolean status field `done` is now renamed to `completed` (`v1_spec.md:19`, `v2_spec.md:36`). The field `done` is no longer supported in request bodies or response structures.

#### Before (v1)
`PUT /tasks/{id}` request payload (`v1_spec.md:68-74`):
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2)
`PUT /v2/tasks/{id}` request payload (`v2_spec.md:100-106`):
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Mandatory `project_id` on Creation
Tasks can no longer exist globally without a project. When creating a task, you must explicitly supply a valid `project_id` in the request body (`v2_spec.md:80-94`). Leaving out this field results in an `HTTP 422 Unprocessable Entity` error.

#### Before (v1)
`POST /tasks` payload (`v1_spec.md:55-60`):
```json
{
  "title": "New task title"
}
```

#### After (v2)
`POST /v2/tasks` payload (`v2_spec.md:84-90`):
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Response Format for List Endpoints
To support scalable pagination, the listing endpoint no longer returns a bare JSON array (`v1_spec.md:31-43`). Instead, it returns an envelope containing a list of `items`, a `total` record count, and a `next_cursor` token for fetching subsequent pages (`v2_spec.md:48-61`).

#### Before (v1)
`GET /tasks` response:
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

#### After (v2)
`GET /v2/tasks` response:
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

To fetch the next page of results, pass the cursor string to the query parameter (`v2_spec.md:60`):
```http
GET /v2/tasks?cursor=cursor_xyz&limit=20
```

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your integration from v1 to v2:

- [ ] **Update Target Base Paths**: Search codebases for endpoints matching `/tasks` and append `/v2` (e.g., `/v2/tasks`).
- [ ] **Switch Authorization Schemes**: Replace `X-Auth-Token` headers with the standard `Authorization: Bearer <your_api_token>` header format.
- [ ] **Change ID Validation Schemas**: Convert database types, class models, and parameter parsers for Task IDs from integers to UUID strings.
- [ ] **Refactor Task States**: Rename instances of `.done` or `["done"]` to `.completed` or `["completed"]` in both frontend parsing and backend models.
- [ ] **Inject Project Scopes**: Update all task creation workflows to source and supply a valid `project_id`.
- [ ] **Rebuild Response Iterators**: Update your client's list parser to extract elements from the response's `.items` property rather than looping over the root array directly, and integrate cursor pagination using the `.next_cursor` property.
- [ ] **Run Migration Tests**: Verify that task operations run cleanly against the v2 mock or sandbox environments.

---

## Upgrade Command

To update your local Zrb CLI installation to the latest v2 release, run:

```bash
pip install --upgrade zrb
```

If you installed Zrb globally using `pipx`, use:

```bash
pipx upgrade zrb
```
