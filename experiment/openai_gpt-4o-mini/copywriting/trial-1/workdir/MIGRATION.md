# Zrb Task API Migration Guide from v1 to v2

## Overview
This guide outlines the breaking changes when migrating from version 1 (v1) to version 2 (v2) of the Zrb Task API, along with examples and a checklist to assist in the transition.

## Breaking Changes

### 1. Endpoint Prefix
- **v1:** `/tasks`
- **v2:** `/v2/tasks`

**Example:**
```http
GET /tasks    
```
becomes
```http
GET /v2/tasks
```

---

### 2. Authentication Header Change
- **v1 Header:** `X-Auth-Token: <your_api_key>`
- **v2 Header:** `Authorization: Bearer <your_api_token>`

**Example:**  
Before:
```http
X-Auth-Token: <your_api_key>
```
After:
```http
Authorization: Bearer <your_api_token>
```

---

### 3. Task ID Type Change
- **v1:** `id` is an integer.
- **v2:** `id` is a UUID string.

**Example:**
```json
// v1
{
  "id": 42,
  "title": "Write tests"
}
```
```json
// v2
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

---

### 4. Task Field Name Change
- **v1:** `done`
- **v2:** `completed`

**Example:**
```json
// v1
{
  "done": true
}
```
```json
// v2
{
  "completed": true
}
```

---

### 5. Project ID Requirement for Task Creation
- **v1:** No `project_id` required.
- **v2:** `project_id` is now required during task creation.

**Example:**
```json
// v1
{
  "title": "New task title"
}
```
```json
// v2
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

---

### 6. Response Format Change for List Endpoints
- **v1:** Returns a bare array of tasks.
- **v2:** Returns a paginated envelope.

**Example:**
```json
// v1
[
  {"id": 1, "title": "Buy milk"},
  {"id": 2, "title": "Ship v1"}
]
```
```json
// v2
{
  "items": [
    {"id": "1", "title": "Buy milk"},
    {"id": "2", "title": "Ship v1"}
  ],
  "total": 2,
  "next_cursor": null
}
```

---

## Migration Checklist
1. Update your API endpoint URL to include `/v2/`.
2. Change your authentication header to use `Authorization: Bearer <your_api_token>`.
3. Update all references to task IDs to use UUID strings instead of integers.
4. Rename all occurrences of the `done` field to `completed`.
5. Ensure `project_id` is included in all task creation requests.
6. Adapt your code to handle paginated responses for all list endpoints.

## Upgrade Command
To upgrade to v2, run:
```sh
npm install zrb-cli@latest
```