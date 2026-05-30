# Zrb CLI v2 Migration Guide

This guide is designed for developers, systems engineers, and API consumers migrating their existing applications, scripts, and automation workflows from Zrb v1 to the newly released Zrb v2.

Zrb v2 introduces robust support for hierarchical projects, standardized cursor-based pagination for scalability, stronger token authentication, and globally unique identifiers (UUIDs) for task objects. While these changes significantly improve system robustness, they introduce several breaking changes across the API surface.

---

## 1. Endpoint Prefix Changes and Project Scope

All API endpoints in Zrb v2 are now prefixed with `/v2`, and task creation now requires a `project_id` to be specified in the request body. In v1, endpoints were located at the root level (e.g., `/tasks`) and did not support multi-project scoping. In v2, omitting `project_id` on task creation requests will result in an HTTP 422 Unprocessable Entity error, and attempting to access v1 endpoints will return an HTTP 404 or 401 error.

Ensure all API clients, webhook receivers, and custom scripts are updated to use the new endpoints and pass the correct project identifiers.

**Before (v1 API Endpoint and Task Creation):**
```http
POST /tasks HTTP/1.1
X-Auth-Token: my_api_key_v1

{
  "title": "Setup local development environment"
}
```

**After (v2 API Endpoint and Task Creation):**
```http
POST /v2/tasks HTTP/1.1
Authorization: Bearer my_api_token_v2

{
  "title": "Setup local development environment",
  "project_id": "proj_abc123"
}
```

---

## 2. Authentication Header Upgrade

To align with modern web security standards, Zrb v2 has replaced the legacy custom authentication header with the standard bearer token scheme.

The new authentication mechanism requires the standard Authorization header with a Bearer token. Any request using the old `X-Auth-Token` header in v2 will be rejected with an HTTP 401 Unauthorized status code.

**Before (v1 Header Authentication):**
```http
GET /tasks HTTP/1.1
X-Auth-Token: standard_api_key_v1
```

**After (v2 Bearer Token Authentication):**
```http
GET /v2/tasks HTTP/1.1
Authorization: Bearer standard_api_key_v2
```

---

## 3. Task Identifier Type Migration

To support decentralized ID generation and prevent entity enumeration, Task IDs have been migrated to UUID strings instead of integers in Zrb v2.

In Zrb v1, task identifiers were auto-incrementing integers (e.g., `42`). In v2, task identifiers are RFC 4122 compliant UUID v4 strings (e.g., `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`). You must update database schemas, frontend routing parameters, and model parsers to expect string types.

**Before (v1 Task Object representation):**
```json
{
  "id": 42,
  "title": "Perform system maintenance",
  "done": false,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**After (v2 Task Object representation):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Perform system maintenance",
  "completed": false,
  "project_id": "proj_abc123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

## 4. Task Completion Field Rename

The task status boolean field done has been renamed to completed in Zrb v2.

This rename provides cleaner API semantics. All endpoints that return or accept task models (such as updates, creation, and listing) use `completed` instead of `done`. Using `done` in a payload in v2 will either be ignored or cause validation errors depending on your parser configuration.

**Before (v1 Task Completion Field):**
```json
{
  "title": "Perform system maintenance",
  "done": true
}
```

**After (v2 Task Completion Field):**
```json
{
  "title": "Perform system maintenance",
  "completed": true
}
```

---

## 5. List Endpoints and Paginated Envelope Responses

In Zrb v1, retrieving lists of tasks via `GET /tasks` returned a simple, bare JSON array of task objects. This is not suitable for scale.

Zrb v2 introduces cursor-based pagination for all list operations. The API no longer returns bare arrays; instead, it returns a JSON object envelope containing metadata and the paginated results list. The envelope includes `items` (the subset of objects), `total` (total records count), and `next_cursor` (the token for fetching the next page via `?cursor=<next_cursor>`).

**Before (v1 Bare Array List Response):**
```json
[
  {"id": 1, "title": "Setup repository", "done": true},
  {"id": 2, "title": "Configure pipeline", "done": false}
]
```

**After (v2 Paginated Envelope Response):**
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "title": "Configure pipeline",
      "completed": false,
      "project_id": "proj_abc123",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 42,
  "next_cursor": "cursor_page_2_xyz"
}
```

---

## Step-by-Step Migration Checklist

To complete the upgrade successfully, follow this comprehensive checklist:

- [ ] **Scan and Update Endpoints**: Locate all API references in your codebase and prepend `/v2` to the route paths.
- [ ] **Revise Authentication Headers**: Transition from the `X-Auth-Token` header to standard `Authorization: Bearer <your_api_token>` headers.
- [ ] **Convert Identifier Parsing**: Modify database schemas, model mappings, and request variables to parse the `id` field as a UUID string rather than an integer.
- [ ] **Update Field References**: Rename all occurrences of the task `done` attribute to `completed` in both requests and response ingestion logic.
- [ ] **Inject Project Scope**: Verify all task creation routines provide the newly mandatory `project_id` payload field.
- [ ] **Refactor List Ingestion**: Rework any collection handling routines to ingest the paginated list envelope format and handle standard cursor queries.
- [ ] **Validate & Execute Upgrade**: Run a suite of integration and integration-smoke tests in your sandbox, then upgrade the package on developer and production environments.

---

## Upgrade Commands

Once all application code has been modified and validated, execute the following command in your terminal to upgrade the CLI to the latest Zrb version:

Using Python pip:
```bash
pip install --upgrade zrb
```

Using pipx (preferred for global CLI installations):
```bash
pipx upgrade zrb
```
