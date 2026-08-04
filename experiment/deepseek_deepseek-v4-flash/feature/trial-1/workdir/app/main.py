from fastapi import Depends, FastAPI, HTTPException
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project, TaskStatus
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    result = tasks
    if status is not None:
        result = [task for task in result if task.status == status]
    if priority is not None:
        result = [task for task in result if task.priority == priority]
    if assigned_to is not None:
        result = [task for task in result if task.assigned_to == assigned_to]
    start = (page - 1) * page_size
    return result[start : start + page_size]


@app.post("/tasks", response_model=Task, status_code=201)
async def create_task(task: TaskCreate, _: str = Depends(require_api_key)):
    if not any(project.id == task.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    new_id = max((t.id for t in tasks), default=0) + 1
    new_task = Task(id=new_id, **task.model_dump())
    tasks.append(new_task)
    return new_task


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, update: TaskUpdate, _: str = Depends(require_api_key)):
    for task in tasks:
        if task.id == task_id:
            for field, value in update.model_dump(exclude_unset=True).items():
                setattr(task, field, value)
            return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, _: str = Depends(require_api_key)):
    for i, task in enumerate(tasks):
        if task.id == task_id:
            tasks.pop(i)
            return
    raise HTTPException(status_code=404, detail="Task not found")
