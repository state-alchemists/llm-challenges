from fastapi import Depends, FastAPI, HTTPException, Query
from typing import List, Optional

from .auth import require_api_key
from .database import projects, tasks
from .models import Project, Task, TaskCreate, TaskStatus, TaskUpdate

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1),
):
    matching = [
        task
        for task in tasks
        if (status is None or task.status == status)
        and (priority is None or task.priority == priority)
        and (assigned_to is None or task.assigned_to == assigned_to)
    ]
    start = (page - 1) * page_size
    return matching[start : start + page_size]


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, _: str = Depends(require_api_key)):
    if not any(project.id == task.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    new_id = max((t.id for t in tasks), default=0) + 1
    created = Task(id=new_id, **task.model_dump())
    tasks.append(created)
    return created


@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, updates: TaskUpdate, _: str = Depends(require_api_key)):
    for index, task in enumerate(tasks):
        if task.id == task_id:
            tasks[index] = task.model_copy(update=updates.model_dump(exclude_unset=True))
            return tasks[index]
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, _: str = Depends(require_api_key)):
    for index, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(index)
    raise HTTPException(status_code=404, detail="Task not found")
