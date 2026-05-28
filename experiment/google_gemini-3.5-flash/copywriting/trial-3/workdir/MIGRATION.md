# Zrb Task API v2 Migration Guide

This guide describes how to migrate your existing integrations from the Zrb Task API v1 to v2. 

v2 introduces support for projects, robust cursor-based pagination, and stricter, standardized authentication. These improvements introduce several breaking changes to the API endpoints, authentication headers, data models, and responses.

---

## Breaking Changes Summary

| Breaking Change | Impacted Component | Severity | Description |
| :--- | :--- | :--- | :--- |
| **1. Endpoint Prefixing** | URL Paths | Major | All resource endpoints are now prefixed with `/v2/` |
| **2. Authentication Header** | Headers | Critical | Authorization header changed from `X-Auth-Token` to `Authorization: Bearer <token>` |
| **3. UUID Task Identifiers** | Data Model | Major | Task `id` changed from an auto-assigned integer to a UUID string |
| **4. Done Flag Renamed** | Data Model / Payload | Major | Task completion field `done` is renamed to `completed` |
| **5. Mandatory `project_id`** | Create Payload | Major | Task creation (`POST`) now requires a valid `project_id` |
| **6. Paginated Responses** | List Response | Major | List endpoints return a paginated object envelope instead of a bare array |

---

## Detailed Breaking Changes & Code Examples

### 1. Endpoint Prefixing (`/v2/`)
To support version coexistence and future updates, all API routes have been moved under the `/v2` namespace.

#### Before (v1)
```http
GET /tasks HTTP/1.1
Host: api.zrb.dev
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Host: api.zrb.dev
```

---

### 2. Authentication Header
The proprietary authentication header `X-Auth-Token` has been deprecated in favor of the standard HTTP `Authorization` Bearer token scheme. v1 header requests will now reject with an `HTTP 401 Unauthorized` status.

#### Before (v1)
```http
GET /tasks HTTP/1.1
X-Auth-Token: zrb_api_token_12345
```

#### After (v2)
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer zrb_api_token_12345
```

---

### 3. UUID Task Identifiers
To prevent ID enumeration and improve distributed system compatibility, task IDs have changed from auto-incrementing integers to standard 36-character UUID strings. Ensure your local databases, routing mechanisms, and object models are updated from integer to string types.

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

### 4. Done Flag Renamed (`done` → `completed`)
The boolean field indicating completion has been renamed from `done` to `completed` for semantic consistency with our broader object design. This affects task objects returned by the API and payloads accepted by the `PUT` update endpoint.

#### Before (v1 PUT Request)
```json
{
  "title": "Updated title",
  "done": true
}
```

#### After (v2 PUT Request)
```json
{
  "title": "Updated title",
  "completed": true
}
```

---

### 5. Mandatory `project_id` on Creation
Tasks must now belong to a project. When creating a task via `POST`, you must specify a valid `project_id` string. Omitting this field results in an `HTTP 422 Unprocessable Entity` validation error.

#### Before (v1 POST Request)
```json
{
  "title": "New task title"
}
```

#### After (v2 POST Request)
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Paginated Responses
To improve performance and reliability for large datasets, list endpoints no longer return a bare array. Instead, they return a structured envelope containing the items list and pagination metadata.

- **Query Parameters:** Use the optional `limit` (defaults to 20) and `cursor` query parameters to manage page sizes and positions.
- **Next Page Retrieval:** Pass the returned `next_cursor` as the `?cursor=<cursor>` query parameter for subsequent pages.

#### Before (v1 List Response)
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

#### After (v2 List Response)
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Buy milk",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "b2c3d4e5-f6a7-8901-bcde-f1234567890a",
      "title": "Ship v1",
      "completed": true,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:45:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

---

## Step-by-Step Migration Checklist

Follow these steps to migrate your code integration from v1 to v2 safely:

- [ ] **Step 1: Update Authentication Headers**
  Convert client configuration to pass the API key via `Authorization: Bearer <your_api_token>` rather than `X-Auth-Token`.
- [ ] **Step 2: Prefix API Endpoint Routes**
  Update base URL configurations or endpoint paths to route through `/v2/` (e.g., `/tasks` to `/v2/tasks`).
- [ ] **Step 3: Migrate Local Database / Identifiers Schemas**
  Alter schemas in your local/client databases storing task IDs to accept 36-character UUID string types instead of auto-incrementing integers.
- [ ] **Step 4: Rename Completion Field to `completed`**
  Search your codebase for all references to the `.done` task field and update them to `.completed`. Check model serialization/deserialization code and any frontend representations.
- [ ] **Step 5: Provide `project_id` on Task Creation**
  Modify task-creation (`POST`) payload builders to include a valid `project_id` attribute. Ensure your application logic is aware of your target projects' identifiers.
- [ ] **Step 6: Refactor Array Parsing for Paginated List Response**
  Adjust the list parser logic for `GET /v2/tasks`. Ensure you extract the task list from the `.items` property of the response object rather than assuming the top-level payload is a bare array. Implement cursor-based pagination loop using the `.next_cursor` metadata if pulling multi-page lists.
- [ ] **Step 7: Verify Integration via Tests**
  Run your test suite against the v2 staging environment to confirm all paths, validation schemas, and pagination mechanisms behave correctly.

---

## Upgrade Command

To update your Zrb CLI client environment to the latest v2 release, execute:

```bash
pip install --upgrade zrb
```
