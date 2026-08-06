from fastapi import FastAPI, HTTPException, Query, Depends
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project, TaskStatus
from .database import tasks, projects, VALID_API_KEYS
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    filtered = tasks
    if status is not None:
        filtered = [t for t in filtered if t.status == status]
    if priority is not None:
        filtered = [t for t in filtered if t.priority == priority]
    if assigned_to is not None:
        filtered = [t for t in filtered if t.assigned_to == assigned_to]
    start = (page - 1) * page_size
    end = start + page_size
    return filtered[start:end]


@app.post("/tasks", response_model=Task, dependencies=[Depends(require_api_key)])
async def create_task(task: TaskCreate):
    # Validate project exists
    if not any(p.id == task.project_id for p in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    # Generate unique ID
    new_id = max((t.id for t in tasks), default=0) + 1
    new_task = Task(id=new_id, **task.model_dump())
    tasks.append(new_task)
    return new_task


@app.put("/tasks/{task_id}", response_model=Task, dependencies=[Depends(require_api_key)])
async def update_task(task_id: int, task_update: TaskUpdate):
    for i, task in enumerate(tasks):
        if task.id == task_id:
            update_data = task_update.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(tasks[i], key, value)
            return tasks[i]
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", dependencies=[Depends(require_api_key)])
async def delete_task(task_id: int):
    for i, task in enumerate(tasks):
        if task.id == task_id:
            tasks.pop(i)
            return {"message": "Task deleted"}
    raise HTTPException(status_code=404, detail="Task not found")


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
