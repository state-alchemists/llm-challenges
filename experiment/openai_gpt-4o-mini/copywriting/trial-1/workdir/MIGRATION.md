# Zrb Task API Migration Guide from v1 to v2

## Introduction
This guide details the breaking changes between Zrb Task API v1 and v2, providing a step-by-step migration process and code examples to assist developers in transitioning smoothly.

## Breaking Changes

### 1. Endpoint URL Changes
All endpoints have been prefixed with `/v2/`.

**Before:**
```plaintext
GET /tasks
```
**After:**
```plaintext
GET /v2/tasks
```

### 2. Authentication Header Changes
The authentication method has changed from using `X-Auth-Token` to a Bearer token.

**Before:**
```plaintext
X-Auth-Token: <your_api_key>
```
**After:**
```plaintext
Authorization: Bearer <your_api_token>
```

Requests using the old method will receive HTTP 401 errors.

### 3. Task ID Type Changed
The `id` field in the Task object has changed from an integer to a UUID string.

**Before:**
```json
{
  "id": 42,
  "title": "Write tests"
}
```
**After:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Write tests"
}
```

### 4. Task Field Renaming
The `done` field has been renamed to `completed`.

**Before:**
```json
{
  "done": false
}
```
**After:**
```json
{
  "completed": false
}
```

### 5. New Project Requirement in Task Creation
The `project_id` field is now required when creating a new task.

**Before:**
```json
{
  "title": "New task title"
}
```
**After:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```
Omitting `project_id` will return HTTP 422.

### 6. Paginated Response Format
The response from list endpoints now comes in a paginated envelope instead of a bare array.

**Before:**
```json
[
  {"id": 1, "title": "Buy milk", "done": false},
  {"id": 2, "title": "Ship v1", "done": true}
]
```
**After:**
```json
{
  "items": [
    {"id": "1", "title": "Buy milk", "completed": false},
    {"id": "2", "title": "Ship v1", "completed": true}
  ],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```

## Step-by-Step Migration Checklist
1. Update all API endpoint URLs to include `/v2/`.
2. Change the authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Update your code to handle task `id` as a UUID string.
4. Rename any usage of the `done` field to `completed`.
5. Ensure all task creation requests include the `project_id`.
6. Modify your code to handle paginated responses from list endpoints.

## Upgrade Command
To upgrade to v2, run:
```plaintext
npm install zrb@latest
``` 

Start your migration to take advantage of the new features and improvements in the Zrb API v2!