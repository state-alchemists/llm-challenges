# Zrb CLI v2 Migration Guide

This document provides a comprehensive migration guide for experienced developers transitioning from Zrb v1 to Zrb v2. The v2 release introduces several key architectural enhancements, including project scoping, standardized authentication, more robust data types, and native list pagination to improve performance and security.

## Summary of Changes

To successfully upgrade to Zrb v2, you must adapt your client applications, scripts, and integrations to handle the breaking changes summarized below:

- **Authentication Header**: Changed from `X-Auth-Token` to standard Bearer token `Authorization` header.
- **Resource ID Types**: Switched task identifiers from integer to UUID string.
- **Boolean Field Rename**: Renamed the task completion boolean state from `done` to `completed`.
- **API Prefix and Project Scope**: Endpoints are now scoped under `/v2/` prefix, and creating tasks now strictly requires `project_id`.
- **List Payload Structure**: List endpoints return a paginated envelope containing metadata and an items array instead of a bare array.

---

## Detailed Breaking Changes

### 1. Global Endpoint Path Prefix `/v2/` and Required `project_id`

All API resource endpoints are now nested under the `/v2/` base path prefix, and creating new tasks now strictly requires passing a valid `project_id` string.

In Zrb v1, tasks were globally scoped and endpoints had no version prefix. In Zrb v2, multi-tenancy is introduced, meaning tasks must belong to a specific project. Omitting the `project_id` in a `POST` request will result in an HTTP `422 Unprocessable Entity` error.

#### Before (v1)
```http
POST /tasks
X-Auth-Token: key_12345

{
  "title": "Setup development environment"
}
```

#### After (v2)
```http
POST /v2/tasks
Authorization: Bearer token_67890

{
  "title": "Setup development environment",
  "project_id": "proj_abc123"
}
```

---

### 2. Upgraded Authentication Header to Bearer Token

The old custom `X-Auth-Token` authentication header has been replaced with the industry-standard `Authorization: Bearer <token>` token format.

Using the legacy `X-Auth-Token` header on any Zrb v2 endpoint will result in an HTTP `401 Unauthorized` response. All clients must be updated to transmit the token using the standardized Authorization scheme.

#### Before (v1)
```http
GET /tasks
X-Auth-Token: my_secret_token_v1
```

#### After (v2)
```http
GET /v2/tasks
Authorization: Bearer my_secret_token_v2
```

---

### 3. Task Identifier Type Upgraded from Integer to UUID

Task resource identifiers have been migrated from auto-assigned integers to standard UUID strings to prevent ID enumeration and facilitate client-side generation.

In v1, tasks utilized sequential integer IDs (e.g., `42`). In v2, all resource IDs conform to the UUID standard, returning unique 36-character hyphenated strings. All downstream databases, code variables, and logic matching against task IDs must support string values.

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

### 4. Boolean Field Rename: `done` renamed to `completed`

The boolean field representing the task completion state has been renamed from `done` to `completed` across all request and response payloads.

Any update requests (e.g., `PUT /v2/tasks/{id}`) attempting to use the deprecated field `done` will be ignored, and the field will remain unmodified. Ensure all serializers, deserializers, and frontend bindings are updated.

#### Before (v1)
```json
{
  "title": "Updated task",
  "done": true
}
```

#### After (v2)
```json
{
  "title": "Updated task",
  "completed": true
}
```

---

### 5. Paginated Response Envelopes for List Endpoints

List endpoints (such as `GET /v2/tasks`) no longer return a bare JSON array. They now return a standardized paginated envelope object containing metadata.

The returned JSON envelope includes an `items` array representing the records, a `total` integer representing the count of matching records, and a `next_cursor` string for cursor-based pagination. If your code directly iterated over the top-level array in v1, you must update it to access the `.items` property.

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

Follow this systematic checklist to migrate your applications and scripts safely from Zrb v1 to v2:

1. **Audit API Credentials**: Retrieve new v2 API keys if your environment requires a separate credential pool.
2. **Update Base URIs**: Modify all request URLs to prefix endpoints with `/v2/` (e.g., change `/tasks` to `/v2/tasks`).
3. **Migrate Header Formats**: Update headers to use `Authorization: Bearer <token>` instead of `X-Auth-Token`.
4. **Refactor Code Models & Databases**: Update task database schemas and model classes to store `id` as a UUID string (36-char length) instead of an integer.
5. **Rename Fields**: Search your code repository for `.done` or `"done"` attributes and replace them with `.completed` or `"completed"`.
6. **Support project_id**: Ensure all task creation pathways are supplied with a valid, non-empty `project_id` parameter.
7. **Refactor List Parsers**: Update JSON parsing logic for list queries to parse the new envelope object and extract records from the `.items` array.
8. **Implement Cursor Pagination**: Add pagination handlers that accept `next_cursor` and query via `?cursor=<cursor>` for large datasets.
9. **Run Integration Tests**: Execute test suites and manually verify that no legacy endpoints or headers remain in use.

---

## Upgrading the Zrb CLI

When your codebase is updated and ready, upgrade your Zrb command-line tool to the latest v2 release using pip:

```bash
pip install --upgrade zrb
```
