from fastapi import FastAPI, HTTPException, Query, Depends
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[str] = Query(default=None),
    priority: Optional[int] = Query(default=None),
    assigned_to: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1),
):
    result = tasks
    if status is not None:
        result = [t for t in result if t.status.value == status]
    if priority is not None:
        result = [t for t in result if t.priority == priority]
    if assigned_to is not None:
        result = [t for t in result if t.assigned_to == assigned_to]
    start = (page - 1) * page_size
    end = start + page_size
    return result[start:end]


@app.post("/tasks", response_model=Task, dependencies=[Depends(require_api_key)])
async def create_task(task_data: TaskCreate):
    for p in projects:
        if p.id == task_data.project_id:
            new_id = max((t.id for t in tasks), default=0) + 1
            task = Task(id=new_id, **task_data.model_dump())
            tasks.append(task)
            return task
    raise HTTPException(status_code=404, detail="Project not found")


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.put("/tasks/{task_id}", response_model=Task, dependencies=[Depends(require_api_key)])
async def update_task(task_id: int, task_data: TaskUpdate):
    for i, task in enumerate(tasks):
        if task.id == task_id:
            update = task_data.model_dump(exclude_unset=True)
            for field, value in update.items():
                setattr(tasks[i], field, value)
            return tasks[i]
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", dependencies=[Depends(require_api_key)])
async def delete_task(task_id: int):
    for i, task in enumerate(tasks):
        if task.id == task_id:
            del tasks[i]
            return {"message": "Task deleted"}
    raise HTTPException(status_code=404, detail="Task not found")
