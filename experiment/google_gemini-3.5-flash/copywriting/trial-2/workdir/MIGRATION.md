# Zrb CLI v2 Migration Guide

Welcome to the official Zrb CLI v2 migration guide! 

This guide is designed to assist developers in upgrading their existing applications and client integrations from Zrb CLI v1 to Zrb CLI v2. Our team has introduced several breaking changes in v2 to support advanced capabilities such as project partitioning, standardized token-based authentication, and cursored database pagination. 

This document describes each of these breaking changes in detail, provides clear before/after examples, and outlines a step-by-step checklist to ensure a seamless upgrade.

---

## Overview of Breaking Changes

The Zrb CLI v2 release changes key assumptions about endpoint pathing, data formats, payload validation, and request authentication. The six breaking changes are:

1. **New API Prefix:** All endpoints are now prefixed with `/v2/` instead of root paths.
2. **Updated Authentication Header:** Header changed from `X-Auth-Token` to standard Bearer token `Authorization: Bearer <token>`.
3. **UUID Task Identifiers:** The task `id` data type changed from an auto-incrementing integer to a UUID string.
4. **Task Done Field Renamed:** The `done` field has been renamed to `completed`.
5. **Mandatory Project ID on Create:** Creating tasks now requires specifying a `project_id`.
6. **Paginated Responses:** List endpoints now return a cursored envelope format instead of a bare list array.

---

## Breakdown of Breaking Changes & Migration Path

### 1. Endpoint Prefixes

To ensure parallel support of v1 and v2 during the deprecation period, all v2 endpoints now have a `/v2/` path prefix. Any legacy endpoint path without this prefix will either point to v1 or return an HTTP 404.

**Before (v1 API Endpoint):**
```http
GET /tasks
```

**After (v2 API Endpoint):**
```http
GET /v2/tasks
```

---

### 2. Authentication Header

The legacy authentication method using the `X-Auth-Token` header has been removed for better security compliance. You must update your authentication header from `X-Auth-Token` to standard `Authorization` header with a `Bearer` token format.

Requests made using the old header format in v2 will be rejected with an HTTP 401 Unauthorized status.

**Before (v1 Authentication Header):**
```http
GET /tasks HTTP/1.1
X-Auth-Token: my_api_key_v1
```

**After (v2 Authentication Header):**
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer my_api_token_v2
```

---

### 3. Task ID Format Change

The unique identifier `id` of a task object has transitioned from a sequential integer to a standard `uuid` format string. This change mitigates ID enumeration attacks and allows client-side UUID generation.

Ensure your database schemas and API deserialization layers are updated to parse string UUIDs instead of 32-bit/64-bit integers.

**Before (v1 Task Object):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 Task Object):**
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

### 4. Status Field Renamed

The task status field has been renamed from `done` in v1 to `completed` in v2. This rename ensures a clearer domain vocabulary as we introduce complex task states.

Ensure your JSON serializers, form models, and frontend state mappings are updated to use `completed` for both task reading and task updating.

**Before (v1 Task Field Update):**
```json
{
  "title": "Updated title",
  "done": true
}
```

**After (v2 Task Field Update):**
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Mandatory Project Association

Task creation in v2 requires partitioning tasks by project. When creating a new task in `/v2`, you must supply a valid `project_id` parameter in the request payload.

Submitting a task creation payload without `project_id` will return an HTTP 422 Unprocessable Entity error.

**Before (v1 Task Creation):**
```json
POST /tasks
{
  "title": "New task title"
}
```

**After (v2 Task Creation):**
```json
POST /v2/tasks
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Cursored List Pagination

To improve performance for large datasets, Zrb v2 replaces bare array list responses with a paginated envelope structure. The envelope returns task items within an `items` array, along with `total` counts and a cursored `next_cursor` string.

**Before (v1 Bare Array List Response):**
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

**After (v2 Paginated Response Envelope):**
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

Developers should use the `?cursor=<next_cursor>` query parameter to navigate subsequent pages instead of using offsets.

---

## Step-by-Step Migration Checklist

Follow these checklist items systematically to safely transition your integration to Zrb v2:

- [ ] **Step 1:** Modify all API endpoint paths in your codebase or client configuration to include the `/v2/` path prefix.
- [ ] **Step 2:** Update your HTTP client authorization middleware to send standard `Authorization: Bearer <your_api_token>` headers rather than `X-Auth-Token`.
- [ ] **Step 3:** Change local schema definitions, types, or models of task IDs from standard integers to standard UUID strings.
- [ ] **Step 4:** Rename JSON property mappings and DTO variables in your serialization code from `done` to `completed`.
- [ ] **Step 5:** Update task creation forms and payloads to retrieve and submit the required `project_id` value.
- [ ] **Step 6:** Refactor list processing logic to extract task items from the `items` array of the new response envelope, and integrate cursored navigation.
- [ ] **Step 7:** Run all automated test suites against a v2 staging environment to verify everything compiles and functions properly.

---

## Upgrading Zrb CLI

When your codebase and API integrations have been updated, you can safely install or upgrade your Zrb CLI tool to version 2.

### Python Environments (pip)

Upgrade via pip:
```bash
pip install --upgrade zrb
```

### Python Applications (pipx)

Upgrade via pipx:
```bash
pipx upgrade zrb
```

### Dependency Managers (poetry)

Update via poetry:
```bash
poetry update zrb
```
