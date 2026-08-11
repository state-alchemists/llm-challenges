from fastapi import FastAPI, HTTPException, Depends, Query
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
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    filters = {}
    if status:
        filters['status'] = status
    if priority:
        filters['priority'] = priority
    if assigned_to:
        filters['assigned_to'] = assigned_to

    filtered_tasks = [task for task in tasks if all(getattr(task, k) == v for k, v in filters.items())]

    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]

@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, x_api_key: str = Depends(require_api_key)):
    if task.project_id not in [p.id for p in projects]:
        raise HTTPException(status_code=404, detail="Project not found")
    new_task_id = max(task.id for task in tasks) + 1
    created_task = Task(id=new_task_id, **task.dict())
    tasks.append(created_task)
    return created_task

@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_update: TaskUpdate, x_api_key: str = Depends(require_api_key)):
    for task in tasks:
        if task.id == task_id:
            for key, value in task_update.dict(exclude_unset=True).items():
                setattr(task, key, value)
            return task
    raise HTTPException(status_code=404, detail="Task not found")

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    for index in range(len(tasks)):
        if tasks[index].id == task_id:
            tasks.pop(index)
            return
    raise HTTPException(status_code=404, detail="Task not found")
