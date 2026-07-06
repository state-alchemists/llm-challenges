# Project Management API

FastAPI project in `feature/trial-3/workdir/app/`. In-memory data store (`database.py`), Pydantic models (`models.py`), API key auth (`auth.py`).

## Architecture

- `app/main.py` — FastAPI app with endpoints
- `app/auth.py` — `require_api_key` dependency: reads `X-API-Key` header, validates against `VALID_API_KEYS`, returns username
- `app/database.py` — in-memory `tasks` and `projects` lists, `VALID_API_KEYS` dict
- `app/models.py` — `Task`, `TaskCreate`, `TaskUpdate`, `Project`, `TaskStatus` (Pydantic)

## Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | /projects | no | list all |
| GET | /tasks | no | filters: status, priority, assigned_to; pagination: page/page_size |
| GET | /tasks/{id} | no | 404 if missing |
| POST | /tasks | yes | validates project_id exists; auto-generates ID; returns 201 |
| PUT | /tasks/{id} | yes | partial update via `TaskUpdate` `exclude_unset`; 404 if missing |
| DELETE | /tasks/{id} | yes | pops from list; 404 if missing |

## Authentication

Keys in `VALID_API_KEYS` dict. Missing/invalid header → 401 `"Invalid or missing API key"`.

## Backlinks
- [2026-07-06 activity](../activity-log/2026/2026-07/2026-07-06.md) — endpoint implementation
