# Zrb CLI v2 Migration Guide

Welcome to the migration guide for transitioning your applications and integrations from Zrb CLI v1 to v2. This document is designed for experienced developers who are currently using v1 and need to migrate their APIs, client libraries, databases, and integrations to v2.

The v2 release introduces several powerful features, including native project scoping, advanced pagination cursors, and stricter security protocols. To achieve these improvements, several breaking changes have been introduced.

---

## Table of Contents
1. [Authentication Header Changes](#1-authentication-header-changes)
2. [Task ID Type Change](#2-task-id-type-change)
3. [Field Renames](#3-field-renames)
4. [Endpoint Prefixing and Project Scoping](#4-endpoint-prefixing-and-project-scoping)
5. [Paginated List Responses](#5-paginated-list-responses)
6. [Migration Checklist](#6-migration-checklist)
7. [Upgrading the CLI](#7-upgrading-the-cli)

---

## 1. Authentication Header Changes

The new authentication scheme replaces the X-Auth-Token header with a standard Authorization Bearer token. This change aligns Zrb CLI with modern security standards and allows integration with standard OAuth2 / JWT identity providers.

Any request sent to v2 using the old `X-Auth-Token` header will fail with an `HTTP 401 Unauthorized` response.

### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key_v1
```

### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token_v2
```

---

## 2. Task ID Type Change

The task id has changed from an integer to a standard UUID string. This change prevents ID enumeration attacks, allows clients to generate offline-safe unique identifiers, and simplifies database replication and scaling.

Ensure that your databases, client-side models, and downstream integrations are updated to support a 36-character UUID string format instead of a 32-bit or 64-bit integer.

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

---

## 3. Field Renames

The boolean status field done has been renamed to completed in v2. This renaming offers a more semantically accurate description of task lifecycle states.

Any payload submitted to `PUT /v2/tasks/{id}` containing the old `done` key will ignore that key. Update all forms, JSON serializers, and state management hooks to use the new `completed` field name.

### Before (v1 Update)
```json
{
  "title": "Updated title",
  "done": true
}
```

### After (v2 Update)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

## 4. Endpoint Prefixing and Project Scoping

In v2, all task endpoints are prefixed with /v2/ and task creation now requires a project_id. All endpoints under `/tasks` have been completely removed. Additionally, task creation payload will be rejected with an `HTTP 422 Unprocessable Entity` if the `project_id` field is missing.

This scoping ensures all tasks belong to a specific workspace or project context, facilitating better organization and multi-tenancy.

### Before (v1 Post)
```http
POST /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: your_api_key_v1
Content-Type: application/json

{
  "title": "New task title"
}
```

### After (v2 Post)
```http
POST /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer your_api_token_v2
Content-Type: application/json

{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

## 5. Paginated List Responses

To prevent performance degradation on large datasets, listing endpoints no longer return a bare JSON array. Instead, they return a structured paginated envelope that includes the active page's items, the total count, and a cursor for fetching subsequent pages.

To fetch the next page of results, pass the returned `next_cursor` as a query parameter: `?cursor=<next_cursor>`. The default limit per page is 20 items.

### Before (v1 List Response)
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
    "created_at": "2024-01-15T10:45:00Z"
  }
]
```

### After (v2 List Response)
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

## 6. Migration Checklist

Use this step-by-step checklist to systematically update your codebase and deployment environments to the Zrb CLI v2 API:

- [ ] **Audit API Clients:** Update the base URL for all client integrations and API SDKs to use the `/v2/` prefix instead of the bare endpoints.
- [ ] **Update Auth Headers:** Modify client request configurations to pass the standard `Authorization: Bearer <token>` header instead of the legacy `X-Auth-Token` header.
- [ ] **Update DB Schemas & ID Models:** Ensure that tasks can store and process `id` values as 36-character UUID strings instead of sequential integers.
- [ ] **Refactor Field References:** Change all database schemas, backend models, frontend templates, forms, and state variables to use `completed` instead of the old `done` field.
- [ ] **Add Project Context:** Ensure that all UI flows and backend worker services that create tasks are passing a valid `project_id` string during creation.
- [ ] **Implement Pagination:** Refactor any API list-parsing utilities to handle the structured JSON response envelope (`items`, `total`, `next_cursor`) and implement cursor-based traversal.
- [ ] **Validate Local Integrations:** Run local test suites against the updated client wrappers to verify end-to-end integration with the v2 API.
- [ ] **Upgrade the Zrb CLI:** Use the upgrade command to install the latest version of the Zrb CLI in your environment.

---

## 7. Upgrading the CLI

To upgrade your Zrb CLI installation to v2, run the appropriate command for your environment:

Using **pipx** (recommended for standalone CLI usage):
```bash
pipx upgrade zrb
```

Using **pip** (for standard Python virtual environments):
```bash
pip install --upgrade zrb
```

Using **poetry** (for projects managing dependencies locally):
```bash
poetry update zrb
```
