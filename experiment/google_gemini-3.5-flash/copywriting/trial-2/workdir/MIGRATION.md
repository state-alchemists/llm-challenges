# Zrb CLI v1 to v2 Migration Guide

Welcome to the migration guide for the Zrb CLI. This document provides a detailed overview of the breaking changes introduced in Zrb v2 and guides you through upgrading your existing v1 applications. Zrb v2 introduces a more robust and secure API with namespaces, UUID identifiers, standardized pagination envelopes, and unified authentication.

If you are currently running a Zrb v1 client or integration, you must update your code to comply with the new v2 API specification before upgrading your Zrb CLI version.

---

## Breaking Changes Summary

Here is a quick summary of the breaking changes between v1 and v2:

1. **Authentication:** The custom API header has been replaced with standard HTTP Bearer token authentication.
2. **Identifier Types:** Task IDs are now UUIDv4 strings rather than auto-incremented integers.
3. **Task Status Field:** The task status boolean field `done` is renamed to `completed`.
4. **Mandatory Project Scoping:** All tasks must belong to a project, requiring `project_id` during task creation.
5. **API Namespacing:** All REST endpoints are prefixed with `/v2/`.
6. **List Response Structure:** List endpoints now return a paginated envelope containing metadata instead of a bare JSON array.

---

## Detailed Changes and Code Examples

This section describes each breaking change in detail along with Before (v1) and After (v2) code examples to assist in your transition.

### 1. Authentication Header Update

Authentication in v1 used a custom header `X-Auth-Token`. In v2, this has been deprecated. The authentication method has changed from `X-Auth-Token` to `Authorization` with a `Bearer` token.

Any request sent with the old `X-Auth-Token` header to v2 endpoints will receive an HTTP 401 Unauthorized response.

**Before (v1):**
```http
GET /tasks
X-Auth-Token: your_api_key_here
```

**After (v2):**
```http
GET /v2/tasks
Authorization: Bearer your_api_token_here
```

---

### 2. Task ID Type Change (Integer to UUID)

In Zrb v1, tasks were identified by auto-incremented integers. In v2, task IDs have been migrated to UUIDv4 strings to facilitate decentralized ID generation and improve security.

The task `id` field has changed from an integer to a UUID string. You must update your databases, clients, and schemas to handle 36-character UUID strings instead of integers.

**Before (v1) Response Payload:**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2) Response Payload:**
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

### 3. Field Rename: done to completed

To align with modern API design standards, the boolean field that represents a task's status has been renamed. The task `done` field has been renamed to `completed` in v2.

Any client code reading or updating this field must be updated. Supplying the `done` field in `PUT /v2/tasks/{id}` requests will be ignored, and you must use `completed` instead.

**Before (v1) Update Request:**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2) Update Request:**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 4. Required project_id and /v2 Path Prefix

All endpoint paths now use the `/v2` prefix, and creating tasks now requires a `project_id` field. Organizing tasks into projects is now mandatory. Omitting `project_id` on task creation requests will result in an HTTP 422 Unprocessable Entity error.

**Before (v1) Creation Request:**
```http
POST /tasks
Content-Type: application/json

{
  "title": "New task title"
}
```

**After (v2) Creation Request:**
```http
POST /v2/tasks
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 5. Paginated List Envelope

In Zrb v1, querying the list endpoint returned a bare JSON array. This pattern does not scale and makes adding pagination metadata difficult. In v2, listing tasks returns a paginated JSON envelope containing `items`, `total` count, and a `next_cursor` pointer.

To retrieve subsequent pages of tasks, pass the cursor value via the `?cursor=<next_cursor>` query parameter.

**Before (v1) Response List:**
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

**After (v2) Response List:**
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

Follow this systematic checklist to migrate your systems from v1 to v2:

- [ ] **Audit Authentication Headers:** Scan all API client configurations and change `X-Auth-Token` headers to standard `Authorization: Bearer <token>` headers.
- [ ] **Update URL Prefixes:** Update base path URLs in your applications to prepend the `/v2` namespace prefix to all endpoints (e.g., `/tasks` becomes `/v2/tasks`).
- [ ] **Migrate Database Schemas for ID:** Change database schemas and model definitions for task `id` fields from integers to UUID strings (char(36) or UUID type).
- [ ] **Rename Status Fields:** Search your codebase for references to the `done` attribute and rename them to `completed` across both model schemas and front-end displays.
- [ ] **Enforce Project Scoping:** Locate task creation calls (`POST /v2/tasks`) and ensure a valid `project_id` is passed inside the request body payload.
- [ ] **Refactor List Integrations:** Update API response parsing logic where lists are fetched. Wrap collection handling so that instead of expecting a bare array directly, it extracts the `items` array from the paginated envelope.
- [ ] **Implement Cursor Pagination:** Adapt your front-end or worker loops to read the `next_cursor` property and supply it as a `?cursor=` query parameter for paginated requests.
- [ ] **Run Integration Tests:** Execute your testing suites against the new v2 endpoints to verify that all request and response models conform to the v2 API contract.

---

## How to Upgrade

Once your client codebase and API consumers have been updated, you can safely upgrade your local installation of Zrb.

To upgrade your Zrb CLI tool to the latest v2 release, run the following upgrade command:

```bash
pip install --upgrade zrb
```
