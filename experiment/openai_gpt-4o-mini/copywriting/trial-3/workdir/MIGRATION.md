# Zrb Task API Migration Guide

## Overview
This guide will help you migrate from Zrb Task API v1 to v2. It highlights all breaking changes, provides code examples, and includes a migration checklist.

## Breaking Changes

### 1. Endpoint Prefix Change
**Old:**
```
GET /tasks
```
**New:**
```
GET /v2/tasks
```

### 2. Authentication Header Change
**Old:**
```
X-Auth-Token: <your_api_key>
```
**New:**
```
Authorization: Bearer <your_api_token>
```
Requests with the old header will result in HTTP 401.

### 3. Task ID Type Change
The `id` field has changed from an integer to a UUID string.
**Old Task Object:**
```json
{
  "id": 42,
}
```
**New Task Object:**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### 4. Task Field Renamed
The `done` field has been renamed to `completed`.
**Old Task Object:**
```json
{
  "done": false
}
```
**New Task Object:**
```json
{
  "completed": false
}
```

### 5. Required Project ID for Task Creation
The `project_id` field is now required when creating a task.
**Old API Request:**
```json
{
  "title": "New task title"
}
```
**New API Request:**
```json
{
  "title": "New task title",
  "project_id": "proj_abc123"
}
```
Omitting the `project_id` will return HTTP 422.

### 6. Paginated List Response
The response for listing tasks is now wrapped in a paginated envelope rather than returning a bare array.
**Old Response:**
```json
[
  {"id": 1, ...},
  {"id": 2, ...}
]
```
**New Response:**
```json
{
  "items": [...],
  "total": 42,
  "next_cursor": "cursor_xyz"
}
```
Pass `?cursor=<next_cursor>` to fetch the next page.

## Migration Checklist
1. Update all API endpoints to include the `/v2/` prefix.
2. Change the authentication header from `X-Auth-Token` to `Authorization: Bearer <your_api_token>`.
3. Update your data structures:
   - Change task `id` from integer to UUID string.
   - Rename `done` to `completed` in all task objects.
4. Ensure to include `project_id` when creating new tasks.
5. Adjust logic to handle paginated responses from list task endpoints.

## Upgrade Command
To upgrade, run the following command:
```bash
zrb upgrade --version 2.0
```