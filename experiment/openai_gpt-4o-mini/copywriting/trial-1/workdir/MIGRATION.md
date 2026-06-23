# Zrb CLI Migration Guide from v1 to v2

## Overview

This migration guide provides a detailed breakdown of the breaking changes introduced in Zrb CLI v2 compared to v1. It includes code examples to assist you in making the necessary adjustments.

---

## Breaking Changes

### 1. Endpoint Prefixing

All endpoints are now prefixed with `/v2/`.

#### **Before:**
```http
GET /tasks
```
#### **After:**
```http
GET /v2/tasks
```

---

### 2. Authentication Header Change

The authentication header has changed from `X-Auth-Token` to a Bearer token format.

#### **Before:**
```http
X-Auth-Token: <your_api_key>
```
#### **After:**
```http
Authorization: Bearer <your_api_token>
```

**Note:** Requests with `X-Auth-Token` will now receive HTTP `401 Unauthorized`.

---

### 3. Task ID Type Change

The task `id` type has changed from an integer to a UUID string.

#### **Before:**
```json
{
  "id": 42,
  "title": "Write tests"
}
```
#### **After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

---

### 4. Field Renaming

The task field `done` has been renamed to `completed`.

#### **Before:**
```json
{
  "done": false
}
```
#### **After:**
```json
{
  "completed": false
}
```

---

### 5. Required Project ID for Task Creation

The task creation request now requires a `project_id` field.

#### **Before:**
```json
{
  "title": "New task title"
}
```
#### **After:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```

**Note:** Omitting the `project_id` will return HTTP `422 Unprocessable Entity`.

---

### 6. Paginated List Envelope

List endpoints now return a paginated envelope instead of a bare array.

#### **Before:**
```json
[
  {"id": 1, "title": "Buy milk"},
  {"id": 2, "title": "Ship v1"}
]
```
#### **After:**
```json
{
  "items": [
    {"id": 1, "title": "Buy milk"},
    {"id": 2, "title": "Ship v1"}
  ],
  "total": 2,
  "next_cursor": "cursor_123"
}
```

**Note:** Use `?cursor=<next_cursor>` to fetch the next page.

---

## Migration Checklist

1. Update all API endpoint URLs to use the `/v2/` prefix.
2. Change the authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Change the type of the `id` from an integer to a UUID string in your application.
4. Rename the `done` field to `completed` in all relevant requests and responses.
5. Ensure that all task creation requests include the `project_id` field.
6. Update the handling of task list responses to accommodate the paginated structure.

---

## Upgrade Command

To upgrade to v2, run the following command:
```
npm install zrb-cli@latest
```