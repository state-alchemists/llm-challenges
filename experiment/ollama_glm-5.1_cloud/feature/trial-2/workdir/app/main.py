from fastapi import Depends, FastAPI, HTTPException, Query
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project
from .database import tasks, projects, _next_task_id
from .auth import require_api_key

app = FastAPI(title="Project Management API")

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20


def _find_project(project_id: int) -> Optional[Project]:
    for project in projects:
        if project.id == project_id:
            return project
    return None


def _find_task(task_id: int) -> Optional[Task]:
    for task in tasks:
        if task.id == task_id:
            return task
    return None


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[str] = Query(default=None),
    priority: Optional[int] = Query(default=None),
    assigned_to: Optional[str] = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1),
):
    filtered = tasks
    if status is not None:
        filtered = [t for t in filtered if t.status == status]
    if priority is not None:
        filtered = [t for t in filtered if t.priority == priority]
    if assigned_to is not None:
        filtered = [t for t in filtered if t.assigned_to == assigned_to]
    start = (page - 1) * page_size
    return filtered[start : start + page_size]


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    task = _find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/tasks", response_model=Task, status_code=201)
async def create_task(task_create: TaskCreate, username: str = Depends(require_api_key)):
    if _find_project(task_create.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    global _next_task_id
    new_task = Task(id=_next_task_id, **task_create.model_dump())
    _next_task_id += 1
    tasks.append(new_task)
    return new_task


@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_update: TaskUpdate, username: str = Depends(require_api_key)):
    task = _find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    update_data = task_update.model_dump(exclude_unset=True)
    updated_task = task.model_copy(update=update_data)
    for i, t in enumerate(tasks):
        if t.id == task_id:
            tasks[i] = updated_task
            break
    return updated_task


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, username: str = Depends(require_api_key)):
    for i, t in enumerate(tasks):
        if t.id == task_id:
            tasks.pop(i)
            return
    raise HTTPException(status_code=404, detail="Task not found")