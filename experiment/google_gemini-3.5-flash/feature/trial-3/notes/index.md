# HUD

## Active Constraints
- API Key must be validated against `database.py`'s `VALID_API_KEYS`.
- POST /tasks, PUT /tasks/{task_id}, and DELETE /tasks/{task_id} endpoints must require authentication.
- Task filtering (`GET /tasks`) must support `status`, `priority`, and `assigned_to` query params.
- Pagination must support `page` and `page_size` query params.

## Recent Insights
- [FastAPI Project Management API](projects/fastapi_api.md)

## Backlinks
(none)
