# FastAPI Project Management API

## Facts & Architecture
- Implements a local in-memory FastAPI project management API with projects and tasks.
- Supports complete CRUD / auth surface end-to-end.

## Core Features Implemented
- Authentication (`X-API-Key` header verified against `VALID_API_KEYS`) via dependency injection.
- Filterable task listing (`GET /tasks`) supporting status, priority, and assigned_to.
- Slice-based pagination for task list endpoint (`page` and `page_size`).
- Task creation (`POST /tasks`) with existence check for `project_id` and auto-generated unique ID.
- Partial updating (`PUT /tasks/{task_id}`) with validation and 404 response.
- Task deletion (`DELETE /tasks/{task_id}`) with authentication and 404 response.

## Backlinks
- [HUD](../index.md)
- [2026-06-19 Log](../activity-log/2026/2026-06/2026-06-19.md)
