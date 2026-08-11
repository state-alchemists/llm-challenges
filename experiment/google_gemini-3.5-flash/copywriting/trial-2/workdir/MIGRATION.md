# Zrb CLI v1 to v2 Migration Guide

Welcome to the migration guide for transitioning your applications and scripts from the Zrb Task API v1 to v2. This document is designed for experienced developers who have an existing integration with Zrb v1 and need a comprehensive walkthrough of all breaking changes, updated schemas, and endpoint definitions introduced in v2.

With the release of Zrb CLI v2, we have introduced several architectural improvements including project isolation, safer authentication mechanisms, standard UUIDs for identifiers, and structured paginated responses. While these changes make the platform more robust and scalable, they do introduce breaking changes to existing client integrations.

---

## High-Level Overview of Breaking Changes

The transition to v2 introduces six major categories of breaking changes. Please review the detailed breakdowns and code examples below to update your client-side implementation.

### 1. Endpoint Path Prefixing and Project ID Requirements
All endpoint paths in v2 must be updated to use the new version prefix. All task requests are now prefixed with `/v2`, and creating a task now strictly requires a valid `project_id` value. If you attempt to access paths without the prefix or make a creation request without a project ID, you will receive an HTTP error.

#### Code Comparison (Create Task)

**Before (v1 API):**
```http
POST /tasks HTTP/1.1
Host: api.zrb.dev
Content-Type: application/json
X-Auth-Token: v1_token_example_123

{
  "title": "Write tests"
}
```

**After (v2 API):**
```http
POST /v2/tasks HTTP/1.1
Host: api.zrb.dev
Content-Type: application/json
Authorization: Bearer v2_token_example_abc

{
  "title": "Write tests",
  "project_id": "proj_abc123"
}
```

---

### 2. Bearer Authentication Format
We have migrated our security architecture to use standard Bearer tokens. Specifically, you must update your API client to send the new `Authorization` header containing a token formatted as a `Bearer` token. Requests presenting the old `X-Auth-Token` header will fail with HTTP 401 Unauthorized.

#### Code Comparison (Authentication Headers)

**Before (v1 API):**
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
X-Auth-Token: old_auth_token_789
```

**After (v2 API):**
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
Authorization: Bearer new_bearer_token_xyz
```

---

### 3. Task ID Data Type
In order to handle large-scale database operations and prevent sequential ID enumeration, the unique identifier for tasks has changed from an integer to a standard `UUID` string format. All clients storing or parsing the ID must be updated to expect a string representation instead of an integer.

#### Code Comparison (Task Representation)

**Before (v1 API):**
```json
{
  "id": 42,
  "title": "Write tests",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 API):**
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

### 4. Status Field Rename
To establish clean API nomenclature, the boolean field denoting status has changed. In v2 of the task representation, the boolean task completion status field `done` is renamed to `completed`. Make sure to update your application serializers, deserializers, and conditional logic.

#### Code Comparison (Update Task)

**Before (v1 API):**
```http
PUT /tasks/42 HTTP/1.1
Host: api.zrb.dev
Content-Type: application/json
X-Auth-Token: old_auth_token_789

{
  "done": true
}
```

**After (v2 API):**
```http
PUT /v2/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890 HTTP/1.1
Host: api.zrb.dev
Content-Type: application/json
Authorization: Bearer new_bearer_token_xyz

{
  "completed": true
}
```

---

### 5. Paginated List Response Envelope
To prevent memory issues with large datasets, list endpoints no longer return a flat, bare JSON array. Instead, they return a structured, paginated object envelope containing metadata and a cursors link.

#### Code Comparison (List Response)

**Before (v1 API):**
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

**After (v2 API):**
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

Follow these steps in your application environment to fully migrate your systems:

- [ ] **Step 1: Prefix endpoints** — Update all API request paths to append `/v2/` as the prefix.
- [ ] **Step 2: Update Authentication** — Replace `X-Auth-Token: <token>` with `Authorization: Bearer <token>` in your request header builder.
- [ ] **Step 3: Revamp task creation payloads** — Ensure that every `POST` request payload contains a valid, non-empty `project_id`.
- [ ] **Step 4: Update database schema and model classes** — Modify the task ID field from integer to UUID string, and update the status attribute from `done` to `completed`.
- [ ] **Step 5: Revise list parsing** — Update list responses to extract the nested `items` array instead of accessing a root-level flat array. Integrate pagination cursor support.
- [ ] **Step 6: Upgrade your Zrb installation** — Update your local and production installations of the Zrb package to version 2.

---

## Upgrade Command

To upgrade the Zrb CLI and Python package to the latest v2 compatible version, execute the following command in your terminal:

```bash
pip install --upgrade zrb
```
