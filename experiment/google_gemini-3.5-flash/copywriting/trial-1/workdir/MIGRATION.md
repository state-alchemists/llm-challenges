# Zrb Task API — v1 to v2 Migration Guide

## Overview

Welcome to the official developer migration guide for transitioning your applications and integrations from the Zrb Task API v1 to v2. 

The v2 release introduces substantial improvements to API structure, data integrity, scoping, and security, including cursor-based pagination, universally unique identifiers, project scoping, and OAuth-compliant token headers. Consequently, several backward-incompatible changes have been introduced. 

This guide is designed for experienced developers who are currently using v1 to safely and systematically migrate client libraries, automated scripts, and front-end/back-end integrations to the new v2 API standard.

---

## Breaking Changes Reference

This section details every breaking change between v1 and v2, providing explicit before-and-after comparisons to guide your refactoring process.

### 1. Global Endpoint Versioning Prefix
In v1, resources were requested directly at the root namespace. To allow for parallel execution of older client integrations during the deprecation period, all v2 paths are now nested under a version prefix.

All endpoints in v2 are prefixed with `/v2` and creating a task now requires a valid `project_id` field.

**Before (v1 Endpoints):**
```http
GET /tasks
GET /tasks/12
POST /tasks
PUT /tasks/12
DELETE /tasks/12
```

**After (v2 Endpoints):**
```http
GET /v2/tasks
GET /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
POST /v2/tasks
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
DELETE /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### 2. Authorization Header Standard
The previous custom authentication header used in v1 is replaced in v2 by standard HTTP header patterns. Using the deprecated v1 header will result in an immediate `401 Unauthorized` response.

The authentication method now uses Bearer token format with the Authorization header.

**Before (v1 Request Headers):**
```http
X-Auth-Token: your_api_token_here
```

**After (v2 Request Headers):**
```http
Authorization: Bearer your_api_token_here
```

---

### 3. Task Identifier Type Transition
To prevent ID predictability risks (such as enumeration attacks) and facilitate concurrent writes in decentralized or offline-first clients, task identifiers have been updated.

The task identifier is now returned and accepted as a unique uuid string instead of an integer.

**Before (v1 Task Representation):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 Task Representation):**
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

### 4. Status Field Renaming
The boolean state tracker of a task has been renamed to better reflect the current state representation across our wider domain model.

The task status field done has been renamed to completed in all API responses and update requests.

**Before (v1 Update Payload):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 Update Payload):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Mandatory Project Scoping
The v2 API introduces projects to enable better resource organizing, team collaboration, and access control. Consequently, a task can no longer exist independently. Creating a task without specifying its parent project will return a `422 Unprocessable Entity` status.

To successfully create a task in v2, clients must specify a project_id.

**Before (v1 Creation Payload):**
```json
{
  "title": "New task title"
}
```

**After (v2 Creation Payload):**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. List Response Pagination Envelope
Returning a bare JSON array in v1 created memory exhaustion vulnerabilities for both clients and servers when processing large tables. To solve this, v2 uses cursor-based pagination. All list endpoints now return an envelope structure wrapping the result set.

The `/v2/tasks` list endpoint now returns a paginated envelope structure rather than a bare JSON array.

**Before (v1 Bare List Array):**
```json
[
  {"id": 1, "title": "Buy milk", "done": false, "created_at": "..."},
  {"id": 2, "title": "Ship v1", "done": true, "created_at": "..."}
]
```

**After (v2 Paginated Envelope):**
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

To request successive pages of tasks, extract the `next_cursor` value from the envelope and append it as a query parameter in subsequent requests:
`GET /v2/tasks?cursor=cursor_xyz&limit=20`

---

## Step-by-Step Migration Checklist

Follow this systematic roadmap to upgrade your client libraries and systems to the new Zrb v2 standards:

- [ ] Modify API URL configurations to insert the `/v2/` path prefix for all task-related endpoints.
- [ ] Migrate the client request engine to construct the standard `Authorization: Bearer <token>` header instead of the legacy `X-Auth-Token` header.
- [ ] Refactor client database schemas, classes, and serialization schemas to handle the primary keys (`id`) as UUID strings.
- [ ] Update JSON parsers, models, and deserializer properties to map the task's active status from `done` to `completed`.
- [ ] Implement support for the mandatory `project_id` parameter inside all task-creation payloads.
- [ ] Rewrite list-processing functions to handle the paginated envelope format, extracting elements from the `items` property.
- [ ] Implement pagination traversal logic to read `next_cursor` and inject it as a query parameter for fetching succeeding pages.
- [ ] Execute comprehensive automated tests using mock v2 responses to verify correct parsing of UUIDs and paginated formats.

---

## Upgrade Command

Once your integrations have been fully adapted to the updated specification, you can safely upgrade the Zrb CLI to the latest major version. Use the following command to update Zrb using pip:

```bash
pip install --upgrade zrb
```
