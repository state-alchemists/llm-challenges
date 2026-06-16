# Zrb Task API — v1 to v2 Migration Guide

Welcome to the Zrb Task API v2 migration guide. The v2 release of the Zrb CLI and associated APIs introduces projects, robust cursor-based pagination, and enhanced authentication security. These improvements introduce several breaking changes for existing integrations. 

This guide is designed to help experienced developers update their current v1 integrations to be fully compatible with the v2 API and CLI.

---

## Overview of Breaking Changes

The table below summarizes the key differences between v1 and v2.

| Feature / Behavior | Version 1 (v1) | Version 2 (v2) | Impact |
| :--- | :--- | :--- | :--- |
| **Endpoint Base URL** | Root-level paths (`/tasks`) | Prefixed with version (`/v2/tasks`) | Medium |
| **Authentication** | `X-Auth-Token` header | `Authorization: Bearer` header | High |
| **Task ID Format** | Auto-incremented Integer | UUID string | High |
| **State Field Name** | `done` (boolean) | `completed` (boolean) | Medium |
| **Task Creation** | No project requirements | Requires a valid `project_id` | High |
| **List Responses** | Bare JSON array (`[...]`) | Paginated JSON envelope (`{"items": [...]}`) | High |

---

## Detailed Migration Steps

### 1. Update Endpoint Paths
All endpoint routes in the v2 API are now prefixed with `/v2/` instead of root-level paths. You must update your API client configuration or base URLs accordingly.

```http
# v1 Endpoint Route
GET /tasks

# v2 Endpoint Route
GET /v2/tasks
```

---

### 2. Update Authentication Headers
For improved security, the v2 API changes the authentication header from X-Auth-Token to Authorization with a Bearer token. Requests attempting to use the deprecated `X-Auth-Token` header will receive an HTTP 401 Unauthorized response.

```http
# v1 Authentication
X-Auth-Token: secret-v1-token-123

# v2 Authentication
Authorization: Bearer secret-v2-token-456
```

---

### 3. Migrate Task ID Type from Integer to UUID
In the v2 API, the task unique ID is represented as a UUID string instead of an integer. Any client-side databases, caching layers, or strongly-typed decoders that expect an integer identifier for tasks must be refactored to support 36-character UUID formats.

```json
// v1 Task Object (Integer ID)
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}

// v2 Task Object (UUID ID)
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

### 4. Rename Task State Field (`done` to `completed`)
In v2, the boolean field done has been renamed to completed in all response and request payloads. This creates a cleaner, more standard naming convention. Ensure that any JSON parsing models or UI components are updated to bind to `completed` instead of `done`.

```json
// v1 Request Body
{
  "title": "Updated title",
  "done": true
}

// v2 Request Body
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Provide Mandatory Project ID on Task Creation
When creating a new task, the request body sent to the /v2/tasks endpoint must include a valid project_id string. Task isolation by projects is a core feature of v2, so leaving this field out will result in an HTTP 422 Unprocessable Entity error.

```json
// v1 POST /tasks Payload
{
  "title": "New task title"
}

// v2 POST /v2/tasks Payload (project_id is required)
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Parse Paginated List Responses
Listing tasks under /v2/tasks returns a paginated JSON envelope instead of a bare array. The response now contains an `items` array representing the records, a `total` count of records, and a `next_cursor` string for fetching subsequent pages with the `?cursor=` parameter.

```json
// v1 GET /tasks Response (Bare JSON Array)
[
  {
    "id": 1,
    "title": "Buy milk",
    "done": false,
    "created_at": "2024-01-15T10:30:00Z"
  }
]

// v2 GET /v2/tasks Response (Paginated Envelope)
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

Follow this checklist to guarantee a smooth transition from v1 to v2:

- [ ] **Step 1: Upgrade CLI & SDKs** — Upgrade the Zrb CLI using the instructions in the section below.
- [ ] **Step 2: Update Auth Tokens** — Replace all `X-Auth-Token` header occurrences with standard bearer token authorization.
- [ ] **Step 3: Prepend Endpoint Routes** — Modify base URL paths to target `/v2/` endpoints.
- [ ] **Step 4: Update Data Models** — Change model field types for task ID from `integer` to `string` (UUID).
- [ ] **Step 5: Rename Task Done Flag** — Find and rename all model properties, variables, and UI keys from `done` to `completed`.
- [ ] **Step 6: Inject Project Context** — Update task creation functions to pass a valid `project_id`.
- [ ] **Step 7: Implement Cursor Pagination** — Refactor list endpoints to read from the `.items` array of the returned JSON envelope and utilize the `.next_cursor` property for pagination.

---

## Upgrading the Zrb CLI

To upgrade your Zrb CLI installation to the latest v2 release, run the following command in your terminal:

```bash
pip install --upgrade zrb
```

If you manage your project dependencies with standard toolchains, you can use these alternatives:

```bash
# Using poetry
poetry update zrb

# Using pipx for global isolation
pipx upgrade zrb

# Using uv
uv pip install --upgrade zrb
```
